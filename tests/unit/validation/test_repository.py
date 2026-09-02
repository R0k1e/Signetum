import subprocess
from pathlib import Path

import pytest

from reposeal.evidence.receipts import (
    ArtifactIdentity,
    EvidenceIdentity,
    EvidenceReceipt,
    ReceiptError,
    ShardOutcome,
    ValidationCompleteness,
    ValidationExecution,
    ValidationProvenance,
)
from reposeal.validation import (
    GateDeclaration,
    GraphContribution,
    ToolDeclaration,
    ValidationShard,
    resolve_validation_graph,
)
from reposeal.validation.execution import ValidationExecutionError, ValidationInputs
from reposeal.validation.repository import (
    ReceiptStore,
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
        configuration=ArtifactIdentity("reposeal.toml", "sha256:" + "c" * 64),
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
    inputs = ValidationInputs("reposeal.toml", (), (), ())

    assert graph.execution_order("member") == ("core:static",)
    assert inputs.configuration_path == "reposeal.toml"


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "reposeal.toml").write_text("schema_version = 2\n", encoding="utf-8")
    (repository / "uv.lock").write_text("lock\n", encoding="utf-8")
    for command in (
        ("git", "init", "-b", "main"),
        ("git", "config", "user.name", "RepoSeal test"),
        ("git", "config", "user.email", "reposeal@example.invalid"),
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
        "reposeal.toml",
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
