"""A failed gate leaves evidence that the next gate in the workspace accounts for."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import signetum.development_store as store
import signetum.gate_records as records
import signetum.lifecycle as lifecycle
from change_fixtures import consolidated_approval
from signetum.change_record import contract_digest, parse_change_record
from signetum.gate_records import failure_path
from signetum.git import git_output
from signetum.validation.execution import ValidationExecutionError
from signetum.workspaces import WorkspaceRecord, write_record

NODE = "tests/test_contract.py::test_contract"

NODES = """import json, os, sys
from pathlib import Path
nodes = json.loads(Path("nodes.json").read_text())
first_failed = [n for n, o in nodes.items() if o in ("failed", "recovered")]
if destination := os.environ.get("SIGNETUM_NODE_REPORT"):
    passed = [n for n, o in nodes.items() if o == "passed"]
    Path(destination).write_text(json.dumps({"failed": first_failed, "passed": passed}))
recovered = [n for n, o in nodes.items() if o == "recovered"]
if recovered and (report := os.environ.get("SIGNETUM_RECOVERY_REPORT")):
    phase = [{"phase": "call", "outcome": "failed"}]
    Path(report).write_text(json.dumps([{"node_id": n, "first_failure": phase} for n in recovered]))
sys.exit(1 if "failed" in nodes.values() else 0)
"""


def _manifest(marker: Path, member_shards: tuple[str, ...]) -> str:
    check = [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()"]
    gates = json.dumps(list(member_shards))
    return f"""schema_version = 5
[delivery]
branch = "main"

[signetum]
protocol = 2

[repository]
architecture = "docs/ARCHITECTURE.md"
changes = "changes"
decisions = "docs/decisions"

[[validation.shards]]
name = "repo:check"
command = {json.dumps([*check, str(marker)])}

[[validation.shards]]
name = "repo:nodes"
command = {json.dumps([sys.executable, "nodes.py"])}

[[validation.shards]]
name = "repo:prepare"
command = ["true"]

[[validation.gates]]
name = "member"
shards = {gates}

[[validation.gates]]
name = "final"
shards = ["repo:check", "repo:nodes"]

[[validation.gates]]
name = "prepare"
shards = ["repo:prepare"]

[[validation.gates]]
name = "batch"
shards = {gates}
"""


def _commit(worktree: Path, message: str) -> None:
    git_output(worktree, "add", ".")
    git_output(worktree, "commit", "-m", message)


def _workspaces(tmp_path: Path, nodes: dict[str, str]) -> tuple[Path, Path, Path]:
    root = tmp_path / "repository"
    root.mkdir()
    marker = tmp_path / "checks-ran"
    git_output(root, "init", "-b", "main")
    git_output(root, "config", "user.name", "Signetum Tests")
    git_output(root, "config", "user.email", "signetum@example.invalid")
    (root / "signetum.toml").write_text(_manifest(marker, ("repo:check", "repo:nodes")))
    (root / "nodes.py").write_text(NODES)
    (root / "nodes.json").write_text(json.dumps({NODE: "passed"}))
    policy = root / ".agents/signetum/repo.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("delivery:\n  branch: main\n")
    _commit(root, "seed")
    base = git_output(root, "rev-parse", "HEAD")
    member, batch = tmp_path / "member", tmp_path / "batch"
    for path, branch, kind in ((member, "impl/member", "member"), (batch, "batch/test", "batch")):
        git_output(root, "worktree", "add", "-b", branch, str(path), base)
        write_record(
            lifecycle._state_root(path),
            WorkspaceRecord(schema_version=1, branch=branch, base=base, kind=kind),
        )
    consolidated_approval(member, base)
    _commit(member, "approve change example")
    (member / "nodes.json").write_text(json.dumps(nodes))
    (member / "feature.txt").write_text("behavior\n")
    _commit(member, "implement the behavior")
    return member, batch, marker


def _remembered(worktree: Path, branch: str) -> dict[str, object]:
    return json.loads(failure_path(worktree, branch).read_text(encoding="utf-8"))


def _record_root_cause(member: Path, node: str) -> None:
    record = parse_change_record((member / "changes/example/change.toml").read_text())
    request = {
        "id": "example/flaky-contract",
        "change_id": "example",
        "operation": "record",
        "approval_digest": contract_digest(record.contract),
        "reason": "The contract test raced a shared temporary directory.",
        "observations": [
            {
                "id": "example/flaky-contract/observation",
                "requirements": ["REQ-1"],
                "summary": "The contract test no longer belongs to this change's selection.",
                "reason": "Root cause: a shared temporary directory raced with cleanup.",
                "evidence": [node],
            }
        ],
    }
    observed = store.append_transaction(
        member, store.parse_request(request), expected_history=store.snapshot(member).history_digest
    )
    store.append_transaction(
        member,
        store.parse_request(
            {
                **request,
                "id": "example/close-contract-root-cause",
                "operation": "resolve",
                "observations": [],
                "resolutions": [
                    {
                        "id": "example/contract-root-cause-answer",
                        "target": "example/flaky-contract/observation",
                        "status": "resolved",
                        "reason": "The selection no longer carries the faulty contract test.",
                        "evidence": ["feature.txt"],
                    }
                ],
            }
        ),
        expected_history=observed.history_digest,
    )
    _commit(member, "record the contract failure root cause")


def test_a_dropped_failure_is_refused_before_checks_until_its_root_cause_is_recorded(tmp_path):
    member, _, marker = _workspaces(tmp_path, {NODE: "failed"})
    with pytest.raises(ValidationExecutionError, match="repo:nodes"):
        lifecycle.validate(member, "member")
    remembered = _remembered(member, "impl/member")
    assert remembered["workspace"] == "impl/member"
    assert remembered["gate"] == "member"
    assert remembered["changes"] == ["example"]
    assert remembered["tip"] == git_output(member, "rev-parse", "HEAD")
    assert remembered["failed"] == [{"shard": "repo:nodes", "node_id": NODE}]
    assert remembered["recovered"] == []
    assert failure_path(member, "impl/member").parent.parent == lifecycle._state_root(member)

    (member / "signetum.toml").write_text(_manifest(marker, ("repo:check",)))
    _commit(member, "drop the failing shard from the member gate")
    marker.unlink(missing_ok=True)
    with pytest.raises(lifecycle.AdmissionError, match=re.escape(NODE)):
        lifecycle.validate(member, "member")
    assert not marker.exists(), "a refused gate must not start checks"

    _record_root_cause(member, NODE)
    assert lifecycle.validate(member, "member")["status"] == "ready"
    assert marker.exists()
    assert not failure_path(member, "impl/member").exists()


def test_a_reselected_failure_needs_no_record_once_it_passes(tmp_path):
    member, _, _ = _workspaces(tmp_path, {NODE: "failed"})
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    (member / "nodes.json").write_text(json.dumps({NODE: "passed"}))
    _commit(member, "repair the contract")
    assert lifecycle.validate(member, "member")["status"] == "ready"
    assert not failure_path(member, "impl/member").exists()


def test_a_reselected_failure_that_does_not_report_passing_fails_the_gate(tmp_path):
    member, _, _ = _workspaces(tmp_path, {NODE: "failed"})
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    (member / "nodes.json").write_text(json.dumps({}))
    _commit(member, "delete the failing contract test")
    with pytest.raises(ValidationExecutionError, match=re.escape(NODE)):
        lifecycle.validate(member, "member")
    assert _remembered(member, "impl/member")["failed"] == [
        {"shard": "repo:nodes", "node_id": NODE}
    ]


def test_a_retry_only_pass_is_remembered_as_failed_and_recovered(tmp_path):
    member, _, _ = _workspaces(tmp_path, {NODE: "recovered"})
    with pytest.raises(ValidationExecutionError, match="cannot be cleared by retry"):
        lifecycle.validate(member, "member")
    remembered = _remembered(member, "impl/member")
    assert remembered["failed"] == [{"shard": "repo:nodes", "node_id": NODE}]
    assert remembered["recovered"] == [{"shard": "repo:nodes", "node_id": NODE}]


def test_a_failed_batch_gate_is_remembered_for_the_batch_workspace(tmp_path):
    member, batch, _ = _workspaces(tmp_path, {NODE: "passed"})
    assert lifecycle.validate(member, "member")["status"] == "ready"
    (batch / "nodes.json").write_text(json.dumps({"tests/test_batch.py::test_join": "failed"}))
    _commit(batch, "integrate a failing repair")
    with pytest.raises(ValidationExecutionError, match="repo:nodes"):
        lifecycle.admit(batch, (member,))
    remembered = _remembered(batch, "batch/test")
    assert remembered["gate"] == "batch"
    assert remembered["tip"] == git_output(batch, "rev-parse", "HEAD")
    assert remembered["failed"] == [
        {"shard": "repo:nodes", "node_id": "tests/test_batch.py::test_join"}
    ]


def test_reselected_failures_need_no_journal_read(tmp_path, monkeypatch):
    # An open batch-continue merge holds a member journal that HEAD cannot yet
    # verify; nodes selected again must pass, so their records are never read.
    monkeypatch.setattr(
        records, "remembered_failures", lambda repository, branch: [("engine:pytest", NODE)]
    )
    monkeypatch.setattr(records, "changed_changes", lambda repository, base: ("member",))

    def unavailable(repository):
        raise ValueError("journal approval is outside the accepted commit ancestry")

    monkeypatch.setattr(records, "snapshot", unavailable)
    owed = records.require_accounted(tmp_path, "batch/x", "a" * 40, {"engine:pytest"})
    assert owed == {"engine:pytest": frozenset({NODE})}
    with pytest.raises(lifecycle.AdmissionError, match="journals are unavailable"):
        records.require_accounted(tmp_path, "batch/x", "a" * 40, set())


def test_a_recorded_root_cause_releases_a_node_whose_shard_stays_selected(tmp_path):
    member, _, _ = _workspaces(tmp_path, {NODE: "failed"})
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    # The one shard holds every test and stays selected; the node no longer runs.
    (member / "nodes.json").write_text(json.dumps({"tests/test_other.py::test_other": "passed"}))
    _commit(member, "replace the failing contract test")
    _record_root_cause(member, NODE)
    assert lifecycle.validate(member, "member")["status"] == "ready"
    assert not failure_path(member, "impl/member").exists()
