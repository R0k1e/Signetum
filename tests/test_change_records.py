"""Recording decisions in change records never costs a validation round."""

import json
from pathlib import Path
from typing import Any

import pytest
from change_fixtures import commit_approval
from signetum import change_cli, lifecycle
from signetum.change_record import contract_digest, parse_change_record
from signetum.development_store import snapshot as development_snapshot
from signetum.workflow_status import workflow_status
from test_batch_admission import _git, _record, _repository


def _manifest(log: Path) -> str:
    def logged(name: str) -> str:
        return json.dumps(["sh", "-c", f"echo {name} >> {log}"])

    return f"""schema_version = 5
[delivery]
branch = "main"

[signetum]
protocol = 2

[repository]
architecture = "docs/ARCHITECTURE.md"
changes = "changes"
decisions = "docs/decisions"

[[impact.rules]]
name = "source"
paths = ["*.txt", "src/**"]
shards = ["repo:static", "repo:tests"]

[[impact.rules]]
name = "documentation"
paths = ["docs/**"]
shards = ["repo:static"]

[validation]
member_required = ["repo:static"]

[[validation.shards]]
name = "repo:static"
command = {logged("static")}

[[validation.shards]]
name = "repo:tests"
inherit = true
command = {logged("tests")}

[[validation.gates]]
name = "member"
shards = ["repo:static", "repo:tests"]

[[validation.gates]]
name = "final"
shards = ["repo:static", "repo:tests"]

[[validation.gates]]
name = "prepare"
shards = []

[[validation.gates]]
name = "batch"
shards = ["repo:static", "repo:tests"]
"""


@pytest.fixture
def workspaces(tmp_path):
    """One approved, implemented member and an open batch, both cut from one base."""
    log = tmp_path / "checks.log"
    root = _repository(tmp_path / "repository")
    (root / "signetum.toml").write_text(_manifest(log))
    _git(root, "commit", "-am", "log every check")
    base = _git(root, "rev-parse", "HEAD")
    member, batch = tmp_path / "member", tmp_path / "batch"
    _git(root, "worktree", "add", "-b", "impl/member", str(member), base)
    _git(root, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(member, "impl/member", base)
    _record(batch, "batch/test", base, "batch")
    commit_approval(member)
    (member / "behavior.txt").write_text("implemented\n")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "implement behavior")
    return member, batch, log


def _checks(log: Path) -> list[str]:
    """Checks run since the last call."""
    ran = log.read_text().split() if log.exists() else []
    log.unlink(missing_ok=True)
    return ran


def _journal(repository: Path, capsys, *arguments: str) -> dict[str, object]:
    capsys.readouterr()
    code = change_cli.main([*arguments, "--repository", str(repository)])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0, payload
    return payload


def _observe(repository: Path, capsys, name: str) -> None:
    _journal(
        repository,
        capsys,
        "record",
        "--change",
        "example",
        "--id",
        name,
        "--requirement",
        "REQ-1",
        "--summary",
        f"Finding {name}.",
        "--reason",
        "Keep the finding with its change.",
    )


def _resolve(repository: Path, capsys, name: str, *evidence: str) -> None:
    _journal(
        repository,
        capsys,
        "resolve",
        "--change",
        "example",
        "--id",
        name + "-answer",
        "--target",
        f"example/{name}/observation",
        "--reason",
        "The existing behavior answers it.",
        *(item for path in evidence for item in ("--evidence", path)),
    )


def test_a_records_only_commit_keeps_readiness_and_needs_no_gate(workspaces, capsys):
    member, batch, log = workspaces
    ready = lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    assert _checks(log)

    _observe(member, capsys, "late")
    _resolve(member, capsys, "late", "behavior.txt")
    record = member / "changes/example/change.toml"
    record.write_text(
        record.read_text().replace('source = "Owner', 'source = "Owner, as clarified in review,', 1)
    )
    _git(member, "add", ".")
    _git(member, "commit", "-m", "record the late finding and clarify the approval source")

    reused = lifecycle.validate(member, "member")
    assert reused["status"] == "ready"
    assert reused["checks_started"] is False
    assert Path(str(reused["receipt"])).name == Path(str(ready["receipt"])).name
    status = workflow_status(
        member, development_snapshot(member), source=_git(member, "rev-parse", "HEAD")
    )
    assert status["receipts"]
    admitted: Any = lifecycle.admit(batch, (member,))
    assert admitted["admitted"][0]["ready_evidence"] == Path(str(ready["receipt"])).name
    assert _checks(log) == []

    final: Any = lifecycle.validate(batch, "final")
    assert sorted(_checks(log)) == ["static", "tests"]
    observations = final["delivery_review"]["source_reconciliation"]["changes"][0]
    assert [item["status"] for item in observations["observations"]] == ["resolved"]


def test_a_contract_change_inherits_shards_its_paths_do_not_affect(workspaces):
    member, _, log = workspaces
    lifecycle.validate(member, "member")
    _checks(log)
    record = member / "changes/example/change.toml"
    text = record.read_text()
    old = contract_digest(parse_change_record(text).contract)
    text = text.replace("Implement the confirmed behavior.", "Implement the clarified behavior.")
    contract = text.split("[change.approval]")[0]
    record.write_text(text.replace(old, contract_digest(parse_change_record(contract).contract)))
    _git(member, "commit", "-am", "re-approve the clarified contract")
    (member / "docs").mkdir()
    (member / "docs/note.md").write_text("Clarified.\n")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "document the clarification")

    result: Any = lifecycle.validate(member, "member")

    assert _checks(log) == ["static"]
    inherited = result["evidence"]["extensions"]["inherited_test_evidence_from"]
    assert inherited["shards"] == ["repo:tests"]


def test_the_batch_answers_and_defers_findings_of_an_admitted_change(workspaces, capsys):
    member, batch, log = workspaces
    ready = lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    receipt = Path(str(ready["receipt"])).name
    _checks(log)

    _observe(batch, capsys, "answered")
    with pytest.raises(AssertionError):
        _resolve(batch, capsys, "answered", "nowhere.txt")
    _resolve(batch, capsys, "answered", "behavior.txt", receipt)
    _observe(batch, capsys, "owed")
    _journal(
        batch,
        capsys,
        "resolve",
        "--change",
        "example",
        "--id",
        "owed-later",
        "--target",
        "example/owed/observation",
        "--disposition",
        "deferred",
        "--reason",
        "The owner deferred it; the edge case handling remains owed.",
    )
    _git(batch, "add", ".")
    _git(batch, "commit", "-m", "answer and defer findings in the batch")
    records = _git(batch, "rev-parse", "HEAD")

    final: Any = lifecycle.validate(batch, "final")

    review = final["delivery_review"]
    assert {"commit": records, "changes": ["example"]} in review["inputs"]["batch_commits"]
    statuses = {
        item["id"]: item["status"]
        for item in review["source_reconciliation"]["changes"][0]["observations"]
    }
    assert statuses == {
        "example/answered/observation": "resolved",
        "example/owed/observation": "deferred",
    }
    [owed] = review["unfinished_work"]
    assert owed["id"] == "example/owed/observation"
    assert owed["change_id"] == "example"
    assert owed["summary"] == "Finding owed."
    assert owed["reason"] == "The owner deferred it; the edge case handling remains owed."
    assert owed["followup"] is None


def _refused(repository: Path, capsys, *arguments: str) -> dict[str, Any]:
    capsys.readouterr()
    code = change_cli.main([*arguments, "--repository", str(repository)])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code != 0, payload
    return payload


def test_resolve_accepts_the_record_id_and_a_node_id_and_status_stays_compact(workspaces, capsys):
    member, _, _ = workspaces
    (member / "tests").mkdir()
    (member / "tests/test_behavior.py").write_text("def test_behavior():\n    pass\n")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "test the behavior")
    _observe(member, capsys, "flaky")
    _observe(member, capsys, "open")
    missing = _refused(member, capsys, "resolve", "--id", "flaky-answer", "--reason", "Fixed.")
    assert "--target" in missing["cause"] and "/observation" in missing["cause"]
    unknown = _refused(
        member,
        capsys,
        *("resolve", "--id", "flaky-answer", "--target", "nothing", "--reason", "Fixed."),
        *("--evidence", "behavior.txt"),
    )
    assert "example/flaky/observation" in unknown["cause"]
    bare = _refused(member, capsys, "resolve", "--target", "flaky", "--evidence", "behavior.txt")
    assert "--id" in bare["cause"] and "--reason" in bare["cause"]

    resolved: Any = _journal(
        member,
        capsys,
        *("resolve", "--id", "flaky-answer", "--target", "flaky"),
        *("--reason", "The test owns its temporary directory."),
        *("--evidence", "tests/test_behavior.py::test_behavior"),
    )

    [observation] = resolved["observations"]
    assert observation["status"] == "resolved"
    assert observation["resolution"]["target"] == "example/flaky/observation"
    assert observation["resolution"]["evidence"] == ["tests/test_behavior.py"]
    compact: Any = _journal(member, capsys, "status")
    assert [item["observation"]["id"] for item in compact["observations"]] == [
        "example/open/observation"
    ]
    assert compact["observation_counts"] == {"pending": 1, "resolved": 1}
    verbose: Any = _journal(member, capsys, "status", "--verbose")
    assert len(verbose["observations"]) == 2
