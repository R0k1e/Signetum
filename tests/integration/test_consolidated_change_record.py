"""Real standalone record reads preserve approval boundaries and source bytes."""

import json
import subprocess
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from signetum.change_record import (
    RecordedApproval,
    approval_view,
    contract_digest,
    parse_change_record,
    validate_change_record,
)


@pytest.fixture(params=["documentation", "bugfix", "feature", "process"])
def record_source(request):
    kind = request.param
    return f'''[change]
schema_version = 1
id = "{kind}"
[change.source]
kind = "human_direction"
summary = "Preserve the original {kind} intent and rationale."
[change.contract]
version = 1
approved_base = "approved-base"
[[change.contract.requirements]]
id = "REQ-1"
outcome = "Expose the {kind} result."
acceptance = ["The existing entrypoint returns that result."]
[[change.contract.excluded]]
statement = "Publish a release."
reason = "Delivery authorization is separate."
[change.execution]
[[change.execution.steps]]
id = "STEP-1"
requirements = ["REQ-1"]
action = "Extend the current owner and verify its public entrypoint."
'''


def read_record(path, frontend):
    runtime = Path(__file__).parents[2] / "template/.agents/repo-dev/runtime"
    script = """
import sys
sys.path.insert(0,sys.argv[1])
from _signetum_runtime.change_record import main
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules
raise SystemExit(main([sys.argv[2]]))
"""
    argv = (
        ["-m", "signetum.change_record", str(path)]
        if frontend == "engine"
        else ["-I", "-S", "-c", script, str(runtime), str(path)]
    )
    result = subprocess.run(  # noqa: S603 -- public isolated reader and explicit fixture paths
        [sys.executable, *argv],
        capture_output=True,
        text=True,
        check=False,
    )
    return result


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_the_standalone_reader_does_not_create_approval_or_modify_records(
    tmp_path,
    record_source,
    frontend,
):
    path = tmp_path / "change.toml"
    path.write_text(record_source)
    result = read_record(path, frontend)
    assert result.returncode == 0, result.stderr
    view = json.loads(result.stdout)
    assert view["stage"] == "draft" and view["approval"] is None
    assert view["source"]["summary"] in record_source
    assert view["contract"]["excluded"][0]["reason"] in record_source
    assert path.read_text() == record_source
    assert sorted(item.name for item in tmp_path.iterdir()) == ["change.toml"]


def test_recorded_approval_binds_behavior_but_not_routine_plan_refinement(record_source):
    record = parse_change_record(record_source)
    approved = replace(
        record,
        approval=RecordedApproval(
            actor="Owner",
            recorded_at=date(2026, 10, 29),
            source="Owner confirmation in review.",
            contract_digest=contract_digest(record.contract),
        ),
    )
    assert approval_view(approved)["stage"] == "approved"
    step = replace(approved.execution.steps[0], action="Use the same owner and a narrower test.")
    refined = replace(approved, execution=replace(approved.execution, steps=(step,)))
    validate_change_record(refined)
    changed = replace(record.contract.requirements[0], outcome="A different behavior.")
    with pytest.raises(ValueError, match="does not bind"):
        validate_change_record(
            replace(approved, contract=replace(record.contract, requirements=(changed,)))
        )


@pytest.mark.parametrize("damage", ["missing", "unknown", "duplicate"])
def test_steps_cannot_omit_invent_or_duplicate_requirement_ownership(record_source, damage):
    record = parse_change_record(record_source)
    if damage == "duplicate":
        record = replace(
            record, contract=replace(record.contract, requirements=record.contract.requirements * 2)
        )
    else:
        steps = (record.execution.steps[0],)
        if damage == "unknown":
            steps = (replace(steps[0], requirements=("UNKNOWN",)),)
        else:
            second = replace(record.contract.requirements[0], id="REQ-2")
            record = replace(
                record,
                contract=replace(
                    record.contract, requirements=(*record.contract.requirements, second)
                ),
            )
        record = replace(record, execution=replace(record.execution, steps=steps))
    with pytest.raises(ValueError, match=r"ownership|owned requirements"):
        validate_change_record(record)


@pytest.mark.parametrize("boundary", ["base", "autonomy", "excluded"])
def test_recorded_approval_cannot_survive_a_changed_execution_boundary(record_source, boundary):
    record = parse_change_record(record_source)
    approval = RecordedApproval(
        actor="Owner",
        recorded_at=date(2026, 10, 29),
        source="Owner confirmation.",
        contract_digest=contract_digest(record.contract),
    )
    if boundary == "base":
        changed = replace(record.contract, approved_base="another-base")
    elif boundary == "autonomy":
        changed = replace(
            record.contract, autonomy=replace(record.contract.autonomy, allowed=("publication",))
        )
    else:
        changed = replace(record.contract, excluded=())
    with pytest.raises(ValueError, match="does not bind"):
        validate_change_record(replace(record, contract=changed, approval=approval))


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_the_reader_refuses_modified_approved_contract_bytes(tmp_path, record_source, frontend):
    digest = contract_digest(parse_change_record(record_source).contract)
    approval = f'''
[change.approval]
actor = "Owner"
recorded_at = 2026-10-29
source = "Owner confirmation in review."
contract_digest = "{digest}"
'''
    path = tmp_path / "change.toml"
    path.write_text(record_source + approval)
    result = read_record(path, frontend)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["stage"] == "approved"
    path.write_text(record_source.replace('outcome = "', 'outcome = "Different ', 1) + approval)
    result = read_record(path, frontend)
    assert result.returncode == 2
    assert not result.stdout
    assert "does not bind" in json.loads(result.stderr)["reason"]
