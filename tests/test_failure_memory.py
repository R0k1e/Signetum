"""A failed gate leaves evidence that the next gate in the workspace accounts for."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

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

NODES = """import json, sys
from pathlib import Path
nodes = json.loads(Path("nodes.json").read_text())
first_failed = [n for n, o in nodes.items() if o in ("failed", "recovered")]
if destination := sys.argv[sys.argv.index("--node-report") + 1]:
    passed = [n for n, o in nodes.items() if o == "passed"]
    Path(destination).write_text(json.dumps({"failed": first_failed, "passed": passed}))
recovered = [n for n, o in nodes.items() if o == "recovered"]
if recovered:
    report = sys.argv[sys.argv.index("--recovery-report") + 1]
    phase = [{"phase": "call", "outcome": "failed"}]
    Path(report).write_text(json.dumps([{"node_id": n, "first_failure": phase} for n in recovered]))
sys.exit(1 if "failed" in nodes.values() else 0)
"""


RUNNER = """import json, sys, time
from pathlib import Path
arguments = sys.argv[1:]
option = lambda name: Path(arguments[arguments.index(name) + 1])
nodes = json.loads(Path("nodes.json").read_text())
owed = json.loads(option("--priority-nodes").read_text())
assert owed["schema_version"] == 1
ordered = [*(n for n in owed["nodes"] if n in nodes), *(n for n in nodes if n not in owed["nodes"])]
ran = [n for n in ordered if nodes[n] not in ("unreached", "hang")]
with option("--observed").open("a") as stream:
    stream.write(json.dumps({"priority": owed["nodes"], "ran": ran}) + "\\n")
failed = [n for n in ran if nodes[n] == "failed"]
# Written before a possible stop, so a time-bound kill still reports what did not run.
option("--node-report").write_text(json.dumps({
    "failed": failed,
    "passed": [n for n in ran if nodes[n] == "passed"],
    "non_failing": {n: nodes[n] for n in ran if nodes[n] not in ("failed", "recovered")},
    "unreached": [n for n in ordered if nodes[n] in ("unreached", "hang")],
}))
if "hang" in nodes.values():
    time.sleep(60)
sys.exit(1 if failed else 0)
"""


def _runner(observed: Path) -> tuple[str, ...]:
    return (
        sys.executable,
        "runner.py",
        "--priority-nodes",
        "{signetum.priority_nodes_file}",
        "--node-report",
        "{signetum.node_report_file}",
        "--observed",
        str(observed),
    )


def _manifest(
    marker: Path, member_shards: tuple[str, ...], nodes_command: tuple[str, ...] = ()
) -> str:
    check = [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()"]
    nodes_command = nodes_command or (
        sys.executable,
        "nodes.py",
        "--node-report",
        "{signetum.node_report_file}",
        "--recovery-report",
        "{signetum.recovery_report_file}",
    )
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
command = {json.dumps(list(nodes_command))}

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


def _workspaces(
    tmp_path: Path, nodes: dict[str, str], nodes_command: tuple[str, ...] = ()
) -> tuple[Path, Path, Path]:
    root = tmp_path / "repository"
    root.mkdir()
    marker = tmp_path / "checks-ran"
    git_output(root, "init", "-b", "main")
    git_output(root, "config", "user.name", "Signetum Tests")
    git_output(root, "config", "user.email", "signetum@example.invalid")
    (root / "signetum.toml").write_text(
        _manifest(marker, ("repo:check", "repo:nodes"), nodes_command)
    )
    (root / "nodes.py").write_text(NODES)
    (root / "runner.py").write_text(RUNNER)
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


def test_a_failing_test_the_member_renames_is_released_and_recorded(tmp_path):
    stable = "tests/test_stable.py::test_stable"
    renamed = "tests/test_contract.py::test_contract_holds"
    member, _, _ = _workspaces(tmp_path, {NODE: "failed", stable: "failed"})
    (member / "tests").mkdir()
    (member / "tests/test_contract.py").write_text("def test_contract():\n    assert False\n")
    _commit(member, "add the contract test")
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    # The contract test is renamed; the stable node, whose file the member never
    # touched, merely goes unreported and stays owed.
    (member / "tests/test_contract.py").write_text("def test_contract_holds():\n    pass\n")
    (member / "nodes.json").write_text(json.dumps({renamed: "passed"}))
    _commit(member, "rename the contract test")
    with pytest.raises(ValidationExecutionError, match=re.escape(stable)) as refusal:
        lifecycle.validate(member, "member")
    assert NODE not in str(refusal.value)

    (member / "nodes.json").write_text(json.dumps({renamed: "passed", stable: "passed"}))
    _commit(member, "repair the stable test")
    ready = lifecycle.validate(member, "member")

    assert ready["status"] == "ready"
    evidence: Any = ready["evidence"]
    details = evidence["extensions"]["shard_details"]["repo:nodes"]
    assert details["released_vanished_nodes"] == [
        {
            "node_id": NODE,
            "retiring_commit": git_output(
                member, "log", "-1", "--format=%H", "--", "tests/test_contract.py"
            ),
            "basis": "name_absent",
        }
    ]
    assert not failure_path(member, "impl/member").exists()


def test_a_retry_only_pass_is_remembered_as_failed_and_recovered(tmp_path, monkeypatch, capsys):
    member, _, _ = _workspaces(tmp_path, {NODE: "recovered"})
    monkeypatch.chdir(member)
    capsys.readouterr()
    assert lifecycle.main(["ready"]) != 0
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "cannot be cleared by retry" in result["cause"]
    assert result["first_attempt_failures"] == [
        {"shard": "repo:nodes", "node_id": NODE, "passed_on_retry": True}
    ]
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


OTHER = "tests/test_contract.py::test_other"
UNCOLLECTED = "tests/slow/"


def _observed(path: Path) -> list[dict[str, list[str]]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_owed_nodes_are_offered_first_without_changing_what_runs(tmp_path):
    observed = tmp_path / "observed.jsonl"
    member, _, _ = _workspaces(tmp_path, {OTHER: "passed", NODE: "failed"}, _runner(observed))
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    (member / "nodes.json").write_text(json.dumps({OTHER: "passed", NODE: "passed"}))
    _commit(member, "repair the contract")
    ready = lifecycle.validate(member, "member")
    assert ready["status"] == "ready"
    first, second = _observed(observed)
    assert first["priority"] == []
    assert second["priority"] == [NODE]
    # Ordering only: the runner still ran every node, owed first.
    assert second["ran"] == [NODE, OTHER] and sorted(first["ran"]) == sorted(second["ran"])
    evidence = ready["evidence"]
    assert isinstance(evidence, dict)
    shards = [item["name"] for item in evidence["execution"]["shards"]]
    assert sorted(shards) == ["repo:check", "repo:nodes"]


def test_unreached_nodes_fail_the_gate_and_are_owed_first_next_time(tmp_path, monkeypatch, capsys):
    # A stage that never collected reports its path; it returns unchanged as an owed entry.
    observed = tmp_path / "observed.jsonl"
    member, _, _ = _workspaces(
        tmp_path, {NODE: "passed", UNCOLLECTED: "unreached"}, _runner(observed)
    )
    monkeypatch.chdir(member)
    assert lifecycle.main(["ready"]) != 0
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["status"] == "failed"
    assert _remembered(member, "impl/member")["unreached"] == [
        {"shard": "repo:nodes", "node_id": UNCOLLECTED}
    ]

    # A later round that again cannot reach the owed node still fails.
    _commit_empty(member, "retry under the same load")
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    (member / "nodes.json").write_text(json.dumps({NODE: "passed", UNCOLLECTED: "passed"}))
    _commit(member, "give the runner room to finish")
    assert lifecycle.validate(member, "member")["status"] == "ready"
    priorities = [entry["priority"] for entry in _observed(observed)]
    assert priorities == [[], [UNCOLLECTED], [UNCOLLECTED]]
    assert not failure_path(member, "impl/member").exists()


def _commit_empty(worktree: Path, message: str) -> None:
    git_output(worktree, "commit", "--allow-empty", "-m", message)


def test_a_runner_stopped_at_its_time_bound_still_reports_unreached_nodes(tmp_path):
    observed = tmp_path / "observed.jsonl"
    member, _, _ = _workspaces(tmp_path, {NODE: "passed", OTHER: "hang"}, _runner(observed))
    manifest = member / "signetum.toml"
    text = manifest.read_text()
    manifest.write_text(
        text.replace('name = "repo:nodes"\n', 'name = "repo:nodes"\ntimeout_seconds = 2\n')
    )
    _commit(member, "bound the runner")
    with pytest.raises(ValidationExecutionError) as failure:
        lifecycle.validate(member, "member")
    assert failure.value.unreached_nodes == (("repo:nodes", OTHER),)
    assert _remembered(member, "impl/member")["unreached"] == [
        {"shard": "repo:nodes", "node_id": OTHER}
    ]


STATIC = """import json, sys
from pathlib import Path
checks = json.loads(Path("checks.json").read_text())
failed = [name for name, outcome in checks.items() if outcome == "failed"]
report = sys.argv[sys.argv.index("--node-report") + 1]
Path(report).write_text(json.dumps({"failed": [], "passed": [], "failed_checks": failed}))
sys.exit(1 if failed else 0)
"""


def _replace_check(member: Path, command: list[str], *, nodes_require_check: bool = False) -> None:
    manifest = member / "signetum.toml"
    text = re.sub(
        r'(name = "repo:check"\ncommand = ).*\n',
        lambda match: match.group(1) + json.dumps(command) + "\n",
        manifest.read_text(),
    )
    if nodes_require_check:
        text = text.replace(
            'name = "repo:nodes"\n', 'name = "repo:nodes"\nrequires = ["repo:check"]\n'
        )
    manifest.write_text(text)


def test_every_failed_shard_and_check_is_recorded_beside_owed_nodes(tmp_path, monkeypatch, capsys):
    member, _, _ = _workspaces(tmp_path, {NODE: "failed"})
    (member / "static.py").write_text(STATIC)
    (member / "checks.json").write_text(
        json.dumps({"doc-links": "failed", "ruff-check": "failed", "typos": "passed"})
    )
    _replace_check(
        member, [sys.executable, "static.py", "--node-report", "{signetum.node_report_file}"]
    )
    _commit(member, "check the corpus statically")
    monkeypatch.chdir(member)
    capsys.readouterr()
    assert lifecycle.main(["ready"]) != 0
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    expected = [
        {"shard": "repo:check", "exit_code": 1, "checks": ["doc-links", "ruff-check"]},
        {"shard": "repo:nodes", "exit_code": 1, "checks": []},
    ]
    assert result["failed_shards"] == expected
    assert [item["node_id"] for item in result["first_attempt_failures"]] == [NODE]
    summary = result["cause"].splitlines()[-1]
    assert all(name in summary for name in ("repo:check", "repo:nodes", "doc-links", "ruff-check"))
    remembered = _remembered(member, "impl/member")
    assert remembered["failed_shards"] == expected
    assert remembered["failed"] == [{"shard": "repo:nodes", "node_id": NODE}]

    # Repairing only the checks leaves the node owed and the record naming its shard alone.
    (member / "checks.json").write_text(json.dumps({"doc-links": "passed", "ruff-check": "passed"}))
    _commit(member, "repair the static checks")
    with pytest.raises(ValidationExecutionError) as failure:
        lifecycle.validate(member, "member")
    assert [item.shard for item in failure.value.failed_shards] == ["repo:nodes"]
    remembered = _remembered(member, "impl/member")
    assert remembered["failed_shards"] == [{"shard": "repo:nodes", "exit_code": 1, "checks": []}]
    assert remembered["failed"] == [{"shard": "repo:nodes", "node_id": NODE}]

    (member / "nodes.json").write_text(json.dumps({NODE: "passed"}))
    _commit(member, "repair the contract")
    assert lifecycle.validate(member, "member")["status"] == "ready"
    assert not failure_path(member, "impl/member").exists()


def test_a_shard_without_a_report_and_one_skipped_after_it_are_both_recorded(tmp_path):
    member, _, _ = _workspaces(tmp_path, {NODE: "passed"})
    _replace_check(member, [sys.executable, "-c", "raise SystemExit(3)"], nodes_require_check=True)
    _commit(member, "declare a failing declaration check")
    with pytest.raises(ValidationExecutionError) as failure:
        lifecycle.validate(member, "member")
    expected = [
        {"shard": "repo:check", "exit_code": 3, "checks": []},
        {"shard": "repo:nodes", "exit_code": None, "checks": [], "skipped_after": ["repo:check"]},
    ]
    assert [item.document() for item in failure.value.failed_shards] == expected
    remembered = _remembered(member, "impl/member")
    assert remembered["failed_shards"] == expected
    assert remembered["failed"] == []


@pytest.mark.parametrize("mode", ["retired", "unchanged", "excluded", "failed", "legacy"])
def test_collection_retirement_requires_a_passing_run_and_a_changed_file(tmp_path, mode):
    node = NODE + "[removed]"
    member, _, _ = _workspaces(tmp_path, {node: "failed"})
    test = member / "tests/test_contract.py"
    test.parent.mkdir()
    test.write_text("def test_contract(): pass\n# removed parameter\n")
    _commit(member, "add parametrized contract")
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    if mode != "unchanged":
        test.write_text("def test_contract(): pass\n")
    (member / "nodes.json").write_text("{}")
    if mode != "legacy":
        runner = member / "nodes.py"
        runner.write_text(
            runner.read_text().replace(
                '{"failed": first_failed, "passed": passed}',
                '{"failed": first_failed, "passed": passed, "not_collected": '
                + ("[]" if mode == "excluded" else repr([node]))
                + "}",
            )
        )
    if mode == "failed":
        (member / "nodes.json").write_text(json.dumps({"other::test_failure": "failed"}))
    _commit(member, "retire parameter and report collection")
    retiring = git_output(member, "rev-parse", "HEAD")
    if mode != "retired":
        with pytest.raises(ValidationExecutionError):
            lifecycle.validate(member, "member")
        remembered: Any = _remembered(member, "impl/member")
        assert {"shard": "repo:nodes", "node_id": node} in remembered["failed"]
        return
    ready = lifecycle.validate(member, "member")
    evidence: Any = ready["evidence"]
    assert evidence["extensions"]["shard_details"]["repo:nodes"]["released_vanished_nodes"] == [
        {"node_id": node, "retiring_commit": retiring, "basis": "not_collected"}
    ]
    assert not failure_path(member, "impl/member").exists()
    # The collecting run settled the obligation: a later gate need not report retirement again.
    (member / "nodes.py").write_text(NODES)
    _commit(member, "use legacy runner again")
    assert lifecycle.validate(member, "member")["status"] == "ready"


def test_packaged_runner_releases_a_removed_parameter_through_ready(tmp_path):
    command = (
        sys.executable,
        "-m",
        "signetum.validation.pytest_runner",
        "--node-report",
        "{signetum.node_report_file}",
        "--priority-nodes",
        "{signetum.priority_nodes_file}",
        "--",
        "-q",
        "-o",
        "addopts=",
        "--rootdir",
        ".",
        "tests",
    )
    member, _, _ = _workspaces(tmp_path, {}, command)
    (member / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    test = member / "tests/test_contract.py"
    test.parent.mkdir()
    test.write_text(
        "import pytest\n@pytest.mark.parametrize('value', ['kept', 'removed'])\n"
        "def test_contract(value): assert value == 'kept'\n"
    )
    _commit(member, "add failing parameter")
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    test.write_text(
        "import pytest\n@pytest.mark.parametrize('value', ['kept'])\n"
        "def test_contract(value): assert value == 'kept'\n"
    )
    _commit(member, "remove retired parameter")
    retiring = git_output(member, "rev-parse", "HEAD")
    ready = lifecycle.validate(member, "member")
    evidence: Any = ready["evidence"]
    assert evidence["extensions"]["shard_details"]["repo:nodes"]["released_vanished_nodes"] == [
        {"node_id": NODE + "[removed]", "retiring_commit": retiring, "basis": "not_collected"}
    ]
    assert not failure_path(member, "impl/member").exists()


@pytest.mark.parametrize(
    "first, second, clears",
    [
        ("unreached", "skipped", True),
        ("failed", "skipped", False),
        ("unreached", "failed", False),
        ("unreached", "xfailed", True),
    ],
)
def test_reaching_repays_only_unreached_debt(tmp_path, monkeypatch, first, second, clears):
    observed = tmp_path / "observed.jsonl"
    member, _, _ = _workspaces(tmp_path, {NODE: first}, _runner(observed))
    monkeypatch.chdir(member)
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    # Another incomplete gate must preserve reachability versus failure provenance.
    if first == "unreached":
        _commit_empty(member, "still not reached")
        with pytest.raises(ValidationExecutionError):
            lifecycle.validate(member, "member")
        assert records.unreached_only(member, "impl/member") == {"repo:nodes": frozenset({NODE})}
    (member / "nodes.json").write_text(json.dumps({NODE: second}))
    _commit(member, "report terminal outcome")
    if clears:
        ready = lifecycle.validate(member, "member")
        evidence = ready["evidence"]
        assert isinstance(evidence, dict)
        details = evidence["extensions"]["shard_details"]["repo:nodes"]
        assert details["discharged_by_reaching"] == [{"node_id": NODE, "outcome": second}]
        assert not failure_path(member, "impl/member").exists()
    else:
        with pytest.raises(ValidationExecutionError):
            lifecycle.validate(member, "member")
        assert _remembered(member, "impl/member")["failed"] == [
            {"shard": "repo:nodes", "node_id": NODE}
        ]
        # Even a later skip must not launder the now-observed failure.
        (member / "nodes.json").write_text(json.dumps({NODE: "skipped"}))
        if second == "skipped":
            _commit_empty(member, "repeat skip after observed failure")
        else:
            _commit(member, "skip after observed failure")
        with pytest.raises(ValidationExecutionError):
            lifecycle.validate(member, "member")


def test_reachability_discharge_survives_another_node_failure(tmp_path, monkeypatch):
    member, _, _ = _workspaces(
        tmp_path, {NODE: "unreached", OTHER: "passed"}, _runner(tmp_path / "observed")
    )
    monkeypatch.chdir(member)
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    (member / "nodes.json").write_text(json.dumps({NODE: "skipped", OTHER: "failed"}))
    _commit(member, "reach one node while another fails")
    with pytest.raises(ValidationExecutionError):
        lifecycle.validate(member, "member")
    memory = _remembered(member, "impl/member")
    assert memory["failed"] == [{"shard": "repo:nodes", "node_id": OTHER}]
    assert memory["unreached"] == []
    assert memory["discharged_by_reaching"] == [
        {"shard": "repo:nodes", "node_id": NODE, "outcome": "skipped"}
    ]


def test_deferred_unreached_debt_keeps_its_origin(tmp_path):
    member, _, _ = _workspaces(tmp_path, {NODE: "passed"})
    records.remember_failure(
        member,
        "impl/member",
        gate="final",
        base=git_output(member, "rev-parse", "HEAD"),
        tip=git_output(member, "rev-parse", "HEAD"),
        error=ValidationExecutionError(unreached_nodes=(("repo:nodes", NODE),)),
        owed={},
    )
    records.settle_failures(
        member, "impl/member", {"repo:nodes": frozenset({NODE})}, ["repo:check"]
    )
    assert records.unreached_only(member, "impl/member") == {"repo:nodes": frozenset({NODE})}
