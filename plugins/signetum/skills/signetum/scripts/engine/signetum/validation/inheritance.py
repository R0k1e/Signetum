"""Reuse nearest-ancestor test evidence for each shard no intervening change affects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from signetum.change.paths import is_record_path
from signetum.evidence.receipts import (
    ArtifactIdentity,
    EvidenceReceipt,
    ReceiptError,
    ValidationSelection,
    verify_gate_evidence,
)
from signetum.git import GitError, git_output
from signetum.impact import ImpactRuleLike, select_paths
from signetum.serialization import ValueDecodeError, load_json
from signetum.validation import ValidationGraph
from signetum.validation.execution import (
    InheritedEvidence,
    ValidationAdapter,
    ValidationInputs,
    build_evidence_identity,
)
from signetum.validation.ratchet import member_values


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
    rules: tuple[ImpactRuleLike, ...],
    graph: ValidationGraph,
    inputs: ValidationInputs,
    adapter: ValidationAdapter,
    receipt_root: Path,
    *,
    selector: Callable[[tuple[str, ...], str, str], ValidationSelection] | None = None,
    records_root: str | None = None,
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
            raw = load_json(text)
            if not isinstance(raw, dict):
                raise ValueDecodeError("receipt must be an object")
            commit = raw["identity"]["commit"]
            if isinstance(commit, str):
                by_commit.setdefault(commit, []).append((path, text))
        except (OSError, ValueError, KeyError, TypeError):
            # A completed lifecycle projection locates a damaged atomic receipt;
            # it never supplies replacement evidence or permits older fallback.
            try:
                projection = path.with_name(path.name.replace("member-", "member-lifecycle-", 1))
                projected = load_json(projection.read_text(encoding="utf-8"))
                if not isinstance(projected, dict):
                    raise ValueDecodeError("projection must be an object")
                commit = projected["source"]
                if isinstance(commit, str):
                    by_commit.setdefault(commit, []).append((path, ""))
            except (OSError, ValueError, KeyError, TypeError):
                # Its source is unknown, so an older receipt cannot be proved
                # to be the nearest observation. Rerun rather than guess.
                return None
    ancestors = git_output(
        repository, "rev-list", "--first-parent", f"{inputs.base}..{current.commit}"
    ).splitlines()[1:]
    nearest = next((commit for commit in ancestors if commit in by_commit), None)
    if nearest is None:
        return None
    intervening = ancestors[: ancestors.index(nearest)]
    # The current tip is excluded from ancestors, but its own change also counts.
    intervening.insert(0, current.commit)
    paths = tuple(
        sorted(
            {
                path
                for commit in intervening
                for path in git_output(
                    repository, "diff", "--name-only", "-z", f"{commit}^", commit, strip=False
                ).split("\0")
                if path
            }
        )
    )
    # Change records feed no inheritable check; source admission judges them.
    paths = tuple(
        path for path in paths if records_root is None or not is_record_path(path, records_root)
    )
    affected: set[str] = set()
    if paths:
        # Impact rules decide per shard; a provider, when declared, refines them.
        selected = (
            select_paths(paths, rules)
            if selector is None
            else selector(paths, nearest, current.commit)
        )
        # A path nothing explains may affect anything; a test file is a path like
        # any other and affects only the shards its explanation names.
        if selected.unexplained:
            return None
        affected.update(selected.shards)
        for gate in selected.gates:
            affected.update(graph.gate(gate).shards)
    declarations = {shard.name: shard for shard in graph.shards}
    # A rerun shard needs fresh output from what it requires; after only orders.
    pending = list(affected)
    while pending:
        name = pending.pop()
        for dependency in declarations[name].requires:
            if dependency not in affected:
                affected.add(dependency)
                pending.append(dependency)
    candidates = inheritable - affected
    if not candidates:
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
            # A historical retry may explain a failure, but it cannot replace
            # fresh normal execution under the current first-failure policy.
            if receipt.extensions.get("recovered_flake_defects", []):
                return None
            # Inherited tests saw the ancestor's bases; a moved baseline reruns them.
            details = receipt.extensions.get("shard_details", {})
            observed = [
                detail.get("member_values")
                for detail in (details.values() if isinstance(details, dict) else ())
                if isinstance(detail, dict)
            ]
            expected_values = member_values(repository, inputs.base, nearest)
            current_values = member_values(repository, inputs.base, current.commit)
            if any(
                value != current_values.get(key)
                for key, value in expected_values.items()
                if key != "contribution_paths"
            ):
                return None
            if not observed or any(item != expected_values for item in observed):
                return None
            outcomes = {outcome.name: outcome for outcome in receipt.execution.shards}
            # A shard without passing evidence of its exact command here reruns.
            reusable = frozenset(
                name
                for name in candidates
                if name in outcomes
                and outcomes[name].command_digest == declarations[name].digest
                and outcomes[name].evidence == "tree"
                and outcomes[name].status == "passed"
            )
            return InheritedEvidence(receipt, path.name, reusable) if reusable else None
        except (GitError, ReceiptError):
            return None
    return None
