import subprocess
import sys
from pathlib import Path

import pytest
from signetum.evidence.receipts import (
    ArtifactIdentity,
    EvidenceIdentity,
    EvidenceReceipt,
    ReceiptError,
    ShardOutcome,
    ValidationCompleteness,
    ValidationExecution,
    ValidationProvenance,
)
from signetum.validation import (
    GateDeclaration,
    GraphContribution,
    ToolDeclaration,
    ValidationShard,
    resolve_validation_graph,
)
from signetum.validation.execution import (
    ValidationExecutionError,
    ValidationInfrastructureError,
    ValidationInputs,
)
from signetum.validation.receipt_store import ReceiptStore
from signetum.validation.repository import (
    RepositoryValidationAdapter,
    run_repository_gate,
    verify_repository_gate,
)


def test_receipt_store_reuses_only_exact_gate_evidence(tmp_path: Path) -> None:
    _outcome = ShardOutcome("core:static", "sha256:" + "4" * 64, "tree", "passed")
    identity = EvidenceIdentity(
        commit="a" * 40,
        tree="b" * 40,
        base=None,
        configuration=ArtifactIdentity("signetum.toml", "sha256:" + "c" * 64),
        profiles=(),
        graph="sha256:" + "d" * 64,
        lockfiles=(),
        tools=(),
    )
    receipt = EvidenceReceipt(
        3,
        "reposeal.validation-evidence@3",
        "sha256:" + "9" * 64,
        identity,
        None,
        ValidationExecution(("final",), (_outcome,)),
        ValidationCompleteness(False, True, ("core:static",)),
        ValidationProvenance(),
        {},
        True,
    )
    store = ReceiptStore(tmp_path)
    written = store.write("final", receipt)

    proven = frozenset({_outcome.command_digest})
    assert store.matching("final", identity, proven) == written

    with pytest.raises(ReceiptError, match="proves the required commands"):
        store.matching("final", identity, frozenset({"sha256:" + "5" * 64}))

    different = EvidenceReceipt(
        3,
        receipt.protocol,
        receipt.schema_digest,
        EvidenceIdentity(
            commit="e" * 40,
            tree=identity.tree,
            base=None,
            configuration=identity.configuration,
            profiles=(),
            graph=identity.graph,
            lockfiles=(),
            tools=(),
        ),
        None,
        receipt.execution,
        receipt.completeness,
        receipt.provenance,
        {},
        True,
    )
    with pytest.raises(ReceiptError, match="proves the required commands"):
        store.matching("final", different.identity, proven)


def test_graph_and_inputs_are_plain_manifest_adapter_values() -> None:
    graph = resolve_validation_graph(
        (
            GraphContribution(
                "core",
                shards=(ValidationShard("core:static", ("check",)),),
                gates=(GateDeclaration("member", ("core:static",)),),
            ),
        )
    )
    inputs = ValidationInputs("signetum.toml", (), (), ())

    assert graph.execution_order("member") == ("core:static",)
    assert inputs.configuration_path == "signetum.toml"


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "signetum.toml").write_text("schema_version = 5\n", encoding="utf-8")
    (repository / "uv.lock").write_text("lock\n", encoding="utf-8")
    for command in (
        ("git", "init", "-b", "main"),
        ("git", "config", "user.name", "Signetum test"),
        ("git", "config", "user.email", "signetum@example.invalid"),
        ("git", "add", "."),
        ("git", "commit", "-m", "initial"),
    ):
        subprocess.run(command, cwd=repository, check=True, capture_output=True)
    return repository


def test_repository_gate_runs_and_reuses_only_the_exact_tree(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    graph = resolve_validation_graph(
        (
            GraphContribution(
                "core",
                shards=(ValidationShard("core:static", ("git", "status", "--short")),),
                gates=(GateDeclaration("final", ("core:static",)),),
            ),
        )
    )
    inputs = ValidationInputs(
        "signetum.toml",
        (),
        ("uv.lock",),
        (ToolDeclaration("git", ("git", "--version")),),
    )
    receipts = tmp_path / "receipts"

    receipt, path = run_repository_gate(repository, graph, "final", inputs, receipts)

    assert path.is_file()
    assert receipt.identity.commit == RepositoryValidationAdapter(repository).commit_identity()
    assert verify_repository_gate(repository, graph, "final", inputs, receipts) == path

    (repository / "uv.lock").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValidationExecutionError, match="worktree is not clean"):
        verify_repository_gate(repository, graph, "final", inputs, receipts)


def test_repository_adapter_refuses_escaping_and_missing_inputs(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    adapter = RepositoryValidationAdapter(repository)

    with pytest.raises(ValidationExecutionError, match="escapes repository"):
        adapter.read_file("../outside")
    with pytest.raises(ValidationExecutionError, match="unavailable"):
        adapter.read_file("missing.lock")


@pytest.mark.parametrize("path", ["uv.lock", "unexpected-source.py"])
def test_validation_cannot_publish_success_after_mutating_inputs(tmp_path, path):
    repository = _repository(tmp_path)
    graph = resolve_validation_graph(
        (
            GraphContribution(
                "fixture",
                (
                    ValidationShard(
                        "test:mutate",
                        (
                            sys.executable,
                            "-c",
                            "from pathlib import Path; import sys; "
                            "Path(sys.argv[1]).write_text('changed')",
                            path,
                        ),
                    ),
                ),
                (GateDeclaration("final", ("test:mutate",)),),
            ),
        )
    )
    receipts = tmp_path / "receipts"
    with pytest.raises(ValidationExecutionError, match=r"inputs changed|worktree is not clean"):
        run_repository_gate(
            repository,
            graph,
            "final",
            ValidationInputs("signetum.toml", (), ("uv.lock",), ()),
            receipts,
        )
    assert not list(receipts.glob("*.json"))


@pytest.mark.parametrize(
    "report",
    [
        "not JSON",
        "{}",
        '[{"node_id": ""}]',
        '[{"node_id":"test_contract","first_failure":[]}]',
        '[{"node_id":"test_contract","first_failure":[{"outcome":"passed"}]}]',
    ],
)
def test_malformed_recovery_evidence_cannot_be_published_as_success(tmp_path, report):
    command = (
        sys.executable,
        "-c",
        "import os, sys; from pathlib import Path; "
        "Path(os.environ['SIGNETUM_RECOVERY_REPORT']).write_text(sys.argv[1])",
        report,
    )
    with pytest.raises(ValidationExecutionError, match="invalid recovery report"):
        RepositoryValidationAdapter(tmp_path).run_shard(ValidationShard("test:recovery", command))


@pytest.mark.parametrize(
    "command",
    [
        (sys.executable, "-c", "pass"),
        (sys.executable, "-c", "raise SystemExit(13)"),
        ("MISSING",),
    ],
)
def test_tool_without_a_successful_nonempty_identity_cannot_supply_evidence(tmp_path, command):
    if command == ("MISSING",):
        command = (str(tmp_path / "missing-identity-command"),)
    with pytest.raises(ValidationInfrastructureError):
        RepositoryValidationAdapter(tmp_path).identify_tool(ToolDeclaration("fixture", command))


def test_non_repository_cannot_supply_a_commit_identity(tmp_path):
    with pytest.raises(ValidationInfrastructureError):
        RepositoryValidationAdapter(tmp_path).commit_identity()


@pytest.mark.parametrize("valid", [False, True])
def test_world_findings_report_must_be_valid_even_when_command_exits_nonzero(tmp_path, valid):
    document = (
        '{"schema_version":1,"findings":[{"id":"fixture-finding",'
        '"locator":"pip:fixture@1.0","summary":"Fixture diagnostic"}]}'
        if valid
        else "not JSON"
    )
    command = (
        sys.executable,
        "-c",
        "import sys; print(sys.argv[1]); raise SystemExit(1)",
        document,
    )
    shard = ValidationShard("test:audit", ("false",), evidence="world", findings_command=command)
    adapter = RepositoryValidationAdapter(tmp_path)
    if valid:
        assert adapter.report_findings(shard)[0].id == "fixture-finding"
    else:
        with pytest.raises(ValidationExecutionError, match="not JSON"):
            adapter.report_findings(shard)


def test_unavailable_findings_command_cannot_produce_a_waivable_report(tmp_path):
    shard = ValidationShard(
        "test:audit",
        ("false",),
        evidence="world",
        findings_command=(str(tmp_path / "missing-findings-command"),),
    )
    with pytest.raises(ValidationInfrastructureError):
        RepositoryValidationAdapter(tmp_path).report_findings(shard)
