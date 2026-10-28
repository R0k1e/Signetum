"""Verify nearest-ancestor test evidence across non-selecting member fixups."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from signetum.evidence.receipts import (
    ArtifactIdentity,
    EvidenceReceipt,
    ReceiptError,
    verify_gate_evidence,
)
from signetum.git import GitError, git_output
from signetum.impact import select_paths
from signetum.manifest import RepositoryManifest
from signetum.validation import ValidationGraph
from signetum.validation.execution import (
    InheritedEvidence,
    ValidationAdapter,
    ValidationInputs,
    build_evidence_identity,
)


def verify_committed_inputs(repository: Path, receipt: EvidenceReceipt) -> None:
    """Verify historical tree and file inputs without executing historical tools."""
    identity = receipt.identity
    if git_output(repository, "rev-parse", f"{identity.commit}^{{tree}}") != identity.tree:
        raise ReceiptError("receipt tree differs from its committed source")
    for artifact in (identity.configuration, *identity.lockfiles):
        content = git_output(
            repository, "show", f"{identity.commit}:{artifact.path}", strip=False
        ).encode()
        if ArtifactIdentity.from_bytes(artifact.path, content) != artifact:
            raise ReceiptError("receipt artifact differs from its committed input")


def find_test_inheritance(
    repository: Path,
    manifest: RepositoryManifest,
    graph: ValidationGraph,
    inputs: ValidationInputs,
    adapter: ValidationAdapter,
    receipt_root: Path,
) -> InheritedEvidence | None:
    """A malformed or incompatible nearest receipt never falls back to an older one."""
    member_names = set(graph.execution_order("member"))
    inheritable = frozenset(
        shard.name for shard in graph.shards if shard.inherit and shard.name in member_names
    )
    if not inheritable or inputs.base is None:
        return None
    current = build_evidence_identity(graph, inputs, adapter)
    by_commit: dict[str, list[tuple[Path, str]]] = {}
    for path in sorted(
        receipt_root.glob("member-*.json"), key=lambda item: item.stat().st_mtime, reverse=True
    ):
        if "-lifecycle-" in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
            raw = json.loads(text)
            commit = raw["identity"]["commit"]
            if isinstance(commit, str):
                by_commit.setdefault(commit, []).append((path, text))
        except (OSError, ValueError, KeyError, TypeError):
            # A completed lifecycle projection locates a damaged atomic receipt;
            # it never supplies replacement evidence or permits older fallback.
            try:
                projection = path.with_name(path.name.replace("member-", "member-lifecycle-", 1))
                commit = json.loads(projection.read_text(encoding="utf-8"))["source"]
                if isinstance(commit, str):
                    by_commit.setdefault(commit, []).append((path, ""))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    ancestors = git_output(
        repository, "rev-list", "--first-parent", f"{inputs.base}..{current.commit}"
    ).splitlines()[1:]
    nearest = next((commit for commit in ancestors if commit in by_commit), None)
    if nearest is None:
        return None
    paths = tuple(
        filter(
            None,
            git_output(
                repository, "diff", "--name-only", "-z", nearest, current.commit, strip=False
            ).split("\0"),
        )
    )
    selected = select_paths(paths, manifest)
    if selected.unexplained or selected.modified_tests:
        return None
    affected = set(selected.shards)
    for gate in selected.gates:
        affected.update(graph.execution_order(gate))
    declarations = {shard.name: shard for shard in graph.shards}
    pending = list(affected)
    while pending:
        name = pending.pop()
        for dependency in declarations[name].requires:
            if dependency not in affected:
                affected.add(dependency)
                pending.append(dependency)
    if affected & inheritable:
        return None
    for path, text in by_commit[nearest]:
        try:
            receipt = EvidenceReceipt.from_json(text)
            tree = git_output(repository, "rev-parse", f"{nearest}^{{tree}}")
            expected = replace(current, commit=nearest, tree=tree)
            verify_gate_evidence(receipt, expected_identity=expected, gate="member")
            if receipt.schema_digest != inputs.schema_digest:
                return None
            verify_committed_inputs(repository, receipt)
            outcomes = {outcome.name: outcome for outcome in receipt.execution.shards}
            if any(
                name not in outcomes
                or outcomes[name].command_digest != declarations[name].digest
                or outcomes[name].evidence != "tree"
                or outcomes[name].status != "passed"
                for name in inheritable
            ):
                return None
            return InheritedEvidence(receipt, path.name, inheritable)
        except (GitError, ReceiptError):
            return None
    return None
