"""Real standalone record reads preserve approval boundaries and source bytes."""

import importlib
import io
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
from signetum.git import git_output


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


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_an_unapproved_change_cannot_claim_completion(tmp_path, record_source, frontend):
    path = tmp_path / "change.toml"
    source = record_source.replace("[change]\n", '[change]\nstatus = "complete"\n', 1)
    path.write_text(source)
    result = read_record(path, frontend)
    assert result.returncode == 2
    assert json.loads(result.stderr)["status"] == "invalid"
    assert path.read_text() == source


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_repository_approval_view_reads_only_the_consolidated_record(
    tmp_path, record_source, frontend, monkeypatch
):
    module = repository_module(frontend, "deviations", monkeypatch)
    record = parse_change_record(record_source)
    source = (
        record_source
        + f'''[change.approval]
actor = "Owner"
recorded_at = 2026-10-29
source = "Owner confirmed the behavior."
contract_digest = "{contract_digest(record.contract)}"
'''
    )
    path = tmp_path / "requests" / record.id / "change.toml"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    before = path.read_bytes()
    view = module.approval_view(tmp_path, record.id, root="requests")
    assert view["schema_version"] == 2
    assert view["requirements"][0]["outcome"] == record.contract.requirements[0].outcome
    assert view["requirements"][0]["acceptance"] == list(record.contract.requirements[0].acceptance)
    assert "outcomes" not in view and "acceptance" not in view
    assert view["requirements"][0]["id"] == "REQ-1"
    assert view["non_goals"][0]["reason"] == "Delivery authorization is separate."
    assert view["approval"]["contract_digest"] == contract_digest(record.contract)
    assert path.read_bytes() == before
    assert sorted(item.name for item in path.parent.iterdir()) == ["change.toml"]


def repository_module(frontend, name, monkeypatch):
    if frontend == "template":
        monkeypatch.syspath_prepend(
            str(Path(__file__).parents[2] / "template/.agents/repo-dev/runtime")
        )
    return importlib.import_module(
        ("signetum." if frontend == "engine" else "_signetum_runtime.") + name
    )


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_traceability_accepts_one_consolidated_record_without_legacy_files(
    tmp_path, record_source, frontend, monkeypatch
):
    module = repository_module(
        frontend, "traceability.cli" if frontend == "engine" else "traceability_cli", monkeypatch
    )
    record = parse_change_record(record_source)
    path = tmp_path / "changes" / record.id / "change.toml"
    path.parent.mkdir(parents=True)
    path.write_text(record_source)
    git_output(tmp_path, "init", "-b", "main")
    out, err = io.StringIO(), io.StringIO()
    assert (
        module.query(
            tmp_path,
            module.TraceabilityManifest(schema_version=1),
            module.EvidenceSnapshot(),
            out,
            err,
        )
        == 0
    ), err.getvalue()
    view = json.loads(out.getvalue())
    assert view["valid"] is True
    assert view["changes"][0]["review"] == record.id
    assert view["changes"][0]["clauses"][0]["state"] == "specified"


def approved_record_source(source):
    record = parse_change_record(source)
    return (
        source
        + f'''[change.approval]
actor = "Owner"
recorded_at = 2026-10-29
source = "Owner confirmed the behavior."
contract_digest = "{contract_digest(record.contract)}"
'''
    )


@pytest.mark.parametrize("frontend", ["engine", "template"])
@pytest.mark.parametrize("damage", ["draft", "stale", "dual", "identity", "symlink", "withdrawn"])
def test_review_refuses_invalid_consolidated_authority_without_legacy_fallback(
    tmp_path, record_source, frontend, damage, monkeypatch
):
    module = repository_module(frontend, "deviations", monkeypatch)
    record = parse_change_record(record_source)
    path = tmp_path / "changes" / record.id / "change.toml"
    path.parent.mkdir(parents=True)
    source = record_source if damage == "draft" else approved_record_source(record_source)
    if damage == "stale":
        source = source.replace(record.contract.requirements[0].outcome, "Another behavior.")
    elif damage == "identity":
        source = source.replace(f'id = "{record.id}"', 'id = "another"', 1)
    elif damage == "withdrawn":
        source = source.replace("[change]", '[change]\nstatus = "withdrawn"', 1)
    path.write_text(source)
    if damage == "dual":
        (path.parent / "review.toml").write_text("Legacy approval must not supply fallback.")
    elif damage == "symlink":
        path.rename(path.with_name("original.toml"))
        path.symlink_to("original.toml")
    with pytest.raises(module.DeviationError):
        module.approval_view(tmp_path, record.id)
    assert path.read_text() == source
    if damage not in {"draft", "withdrawn"}:
        query_module = repository_module(
            frontend,
            "traceability.cli" if frontend == "engine" else "traceability_cli",
            monkeypatch,
        )
        git_output(tmp_path, "init", "-b", "main")
        out, err = io.StringIO(), io.StringIO()
        assert (
            query_module.query(
                tmp_path,
                query_module.TraceabilityManifest(schema_version=1),
                query_module.EvidenceSnapshot(),
                out,
                err,
            )
            != 0
        )
        assert json.loads(out.getvalue())["valid"] is False


@pytest.mark.parametrize("frontend", ["engine", "template"])
@pytest.mark.parametrize("target", ["valid", "missing", "wrong-requirement", "withdrawn"])
def test_traceability_requires_exact_active_transfer_ownership(
    tmp_path, record_source, frontend, target, monkeypatch
):
    module = repository_module(
        frontend, "traceability.cli" if frontend == "engine" else "traceability_cli", monkeypatch
    )
    record = parse_change_record(record_source)
    destination = "following/MISSING" if target == "wrong-requirement" else "following/REQ-1"
    source = (
        record_source
        + f'''[[change.contract.transferred]]
id = "REQ-OLD"
statement = "Carry the explicit follow-up outcome."
target = "{destination}"
'''
    )
    path = tmp_path / "changes" / record.id / "change.toml"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    if target != "missing":
        following = path.parent.parent / "following/change.toml"
        following.parent.mkdir()
        text = record_source.replace(f'id = "{record.id}"', 'id = "following"', 1)
        if target == "withdrawn":
            text = text.replace("[change]", '[change]\nstatus = "withdrawn"', 1)
        following.write_text(text)
    git_output(tmp_path, "init", "-b", "main")
    out, err = io.StringIO(), io.StringIO()
    result = module.query(
        tmp_path, module.TraceabilityManifest(schema_version=1), module.EvidenceSnapshot(), out, err
    )
    assert result == (0 if target == "valid" else 3), err.getvalue()
    if target != "valid":
        assert json.loads(out.getvalue())["issues"][0]["code"] == "invalid-transfer"


@pytest.mark.parametrize("frontend", ["engine", "template"])
@pytest.mark.parametrize(
    "phase", ["ready", "integrated", "delivered", "complete", "foreign", "draft"]
)
def test_consolidated_progress_requires_matching_evidence_and_never_implies_human_acceptance(
    record_source, frontend, phase, monkeypatch
):
    records = repository_module(frontend, "change_record", monkeypatch)
    states = repository_module(
        frontend, "status.models" if frontend == "engine" else "status_models", monkeypatch
    )
    projector = repository_module(
        frontend, "status.projector" if frontend == "engine" else "status_projector", monkeypatch
    )
    source = record_source if phase == "draft" else approved_record_source(record_source)
    record = records.parse_change_record(source)
    path = f"changes/{record.id}/change.toml"
    if phase == "complete":
        record = replace(record, status="complete")
    members = (
        ()
        if phase == "complete"
        else (
            states.MemberObservation(
                plan_id="other/change.toml" if phase == "foreign" else path,
                commit="member",
                ready=True,
            ),
        )
    )
    evidence = states.EvidenceSnapshot(
        members=members,
        integrations=(states.IntegrationObservation(member_commit="member", batch_commit="batch"),)
        if phase in {"integrated", "delivered"}
        else (),
        deliveries=(states.DeliveryObservation(batch_commit="batch", delivery_commit="delivery"),)
        if phase == "delivered"
        else (),
    )
    result = projector.project_record_status(path, record, evidence)
    expected = {"complete": "implementing", "foreign": "implementing", "draft": "specified"}.get(
        phase, phase
    )
    assert result.state == expected
    assert all(item.state == expected for item in result.clauses)
    assert result.state != "accepted"
