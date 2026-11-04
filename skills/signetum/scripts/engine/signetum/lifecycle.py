"""Lifecycle authority for explicit Signetum batch admission."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess  # nosec B404 -- fixed tuple commands, never a shell
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from shutil import which

from signetum.change.member import qualify_member
from signetum.change.scope import (
    delivered_plans,
)
from signetum.decision_claims import clause_claims, owning_workspace, require_distinct_claims
from signetum.delivery import publish_batch
from signetum.development_store import DevelopmentReviewError
from signetum.deviations import (
    DeviationError,
)
from signetum.evidence.receipts import ValidationSelection
from signetum.execution_review import execution_review_inputs
from signetum.gate_records import (
    forget_failures,
    record_verified_batch,
    remember_failure,
    require_accounted,
    verified_batch_tip,
)
from signetum.git import GitError, GitInfrastructureError, git_output, repository_path, run_git
from signetum.lifecycle_validation import validate_workspace
from signetum.manifest import RepositoryManifest, load_manifest
from signetum.operation_cli import OperationParser, run_operation
from signetum.operations import (
    AdmissionError,
    InfrastructureError,
    MergeConflict,
    OperationFailed,
)
from signetum.policy import delivery_policy
from signetum.provenance import attested_base as _attested_base
from signetum.provenance import members_and_plans as _delivery_provenance
from signetum.repository_selection import select_repository
from signetum.synchronization import member_contribution_paths
from signetum.validation import ValidationGraph
from signetum.validation.admission import find_member_evidence
from signetum.validation.configuration import member_shards as _member_shards
from signetum.validation.configuration import with_deferred_world
from signetum.validation.execution import (
    ValidationExecutionError,
    build_evidence_identity,
    execute_gate,
)
from signetum.validation.ratchet import member_environment
from signetum.validation.repository import (
    RepositoryValidationAdapter,
    run_diagnostic_gate,
)
from signetum.validation.repository import configured_validation as _runtime_validation
from signetum.workspace_operations import cleanup_delivered as _cleanup_delivered_worktrees
from signetum.workspace_operations import (
    fresh_delivery,
    open_workspace,
    workspace_open,
    worktree_prepare,
)
from signetum.workspaces import (
    WorkspaceError,
    advance_batch_base,
    read_record,
)
from signetum.workspaces import (
    branch_name as _branch,
)
from signetum.workspaces import (
    exclusive_batch as _exclusive_batch,
)
from signetum.workspaces import (
    recorded_base as _recorded_base,
)
from signetum.workspaces import (
    require_clean as _require_clean,
)
from signetum.workspaces import (
    require_no_merge as _require_no_merge,
)
from signetum.workspaces import (
    state_root as _state_root,
)


def _receipt_root(repository: Path) -> Path:
    root = _state_root(repository) / "validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _selection(repository: Path, base: str, manifest: RepositoryManifest) -> ValidationSelection:
    files = member_contribution_paths(repository, base, _git(repository, "rev-parse", "HEAD"))
    return select_repository(
        repository, manifest, files, base=base, source=_git(repository, "rev-parse", "HEAD")
    ).selection


def changed(repository: Path, explain: bool) -> dict[str, object]:
    _require_clean(repository)
    base = _recorded_base(repository)
    source = _git(repository, "rev-parse", "HEAD")
    manifest = load_manifest(repository / "signetum.toml")
    files = member_contribution_paths(repository, base, source)
    resolved = select_repository(repository, manifest, files, base=base, source=source)
    manifest, selected = resolved.manifest, resolved.selection
    if not files:
        raise AdmissionError("workspace has no committed contribution to validate")
    member_shards, deferred = _member_shards(manifest, selected, member_closure=False)
    if manifest.impact.provider is not None:
        selected = with_deferred_world(selected, deferred)
    _runtime_validation(manifest, member_shards=member_shards)
    if _git(repository, "rev-parse", "HEAD") != source:
        raise ValidationExecutionError("diagnostic changed the committed source")
    try:
        _require_clean(repository)
    except AdmissionError as error:
        raise ValidationExecutionError("diagnostic changed working files") from error
    return {
        "schema_version": 1,
        "status": "selection-only",
        "base": base,
        "source": source,
        "files": files,
        "selection": json.loads(json.dumps(selected.__dict__)),
        "rules": selected.rules,
        "profiles": selected.profiles,
        "gates": selected.gates,
        "shards": selected.shards,
        "unexplained": selected.unexplained,
        "requires_final": selected.requires_final,
        "explain": explain,
        "executed": [],
        "checks_started": False,
        "deferred_world_shards": deferred,
    }


def _drop_qualification(parent: Path, repository: Path) -> OSError | None:
    error: OSError | None = None
    try:
        shutil.rmtree(parent)
    except OSError as caught:
        error = caught
    run_git(repository, "worktree", "prune")
    return error


def _ready_member(repository: Path) -> dict[str, object]:
    """Prepare and check a detached checkout of the committed tip.

    The editing worktree stays. Ignored files that are not in the commit are
    absent from this checkout. Cleanup removes the directory and prunes the
    registration; it does not use ``git worktree remove``.
    """

    _require_clean(repository)
    source = _git(repository, "rev-parse", "HEAD")
    parent = Path(tempfile.mkdtemp(prefix="signetum-ready-"))
    execution = parent / "tree"
    try:
        _git(repository, "worktree", "add", "--detach", str(execution), source)
        graph, _inputs = _runtime_validation(load_manifest(execution / "signetum.toml"))
        if any(gate.name == "prepare" for gate in graph.gates):
            worktree_prepare(execution)
        if _git(execution, "rev-parse", "HEAD") != source:
            raise AdmissionError("qualification worktree is not the member commit")
        result = _validate_held(repository, "member", execution_root=execution)
    finally:
        removal_error = _drop_qualification(parent, repository)
    if removal_error is not None:
        raise InfrastructureError(
            f"qualification worktree could not be removed: {parent}"
        ) from removal_error
    return result


def validate(repository: Path, kind: str) -> dict[str, object]:
    if kind == "member":
        return _ready_member(repository)
    if kind != "final":
        return _validate_held(repository, kind)
    with _exclusive_batch(repository):
        record = read_record(_state_root(repository), _branch(repository))
        if record.kind != "batch":
            raise AdmissionError("final requires a registered batch workspace")
        _require_no_merge(repository)
        _require_clean(repository)
        proposals = _proposal_paths(repository)
        if proposals:
            raise AdmissionError(f"final refuses proposal decisions: {', '.join(proposals)}")
        return _validate_held(repository, kind)


def _validate_held(
    repository: Path, kind: str, *, execution_root: Path | None = None
) -> dict[str, object]:
    return validate_workspace(
        repository,
        kind,
        configure=_runtime_validation,
        adapter_factory=RepositoryValidationAdapter,
        receipt_root=_receipt_root,
        proposal_paths=_proposal_paths,
        check_numbering_base=_require_numbering_base,
        execute=execute_gate,
        execution_root=execution_root,
    )


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    try:
        return git_output(repository, *arguments, check=check)
    except GitError as error:
        raise AdmissionError(str(error)) from error


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    git = _git_executable()
    completed = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "merge-base", "--is-ancestor", ancestor, descendant),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in (0, 1):
        raise AdmissionError(completed.stderr.strip() or "merge-base failed")
    return completed.returncode == 0


def _admission_evidence(member: Path, tip: str, manifest: RepositoryManifest) -> str:
    """Require successful tree evidence for this exact member and its inputs."""

    base = _recorded_base(member)
    if not _is_ancestor(member, base, tip):
        raise AdmissionError("member does not descend from its recorded base")
    declared_manifest = manifest
    resolved = select_repository(
        member, manifest, member_contribution_paths(member, base, tip), base=base, source=tip
    )
    manifest, selection = resolved.manifest, resolved.selection
    required_names, deferred = _member_shards(manifest, selection)
    selection = with_deferred_world(selection, deferred)
    graph, inputs = _runtime_validation(manifest, member_shards=required_names)
    closure = set(graph.execution_order("member"))
    required = frozenset(shard.digest for shard in graph.shards if shard.name in closure)
    adapter = RepositoryValidationAdapter(member)
    member_identity = build_evidence_identity(graph, replace(inputs, base=base), adapter)
    final_graph, _ = _runtime_validation(declared_manifest)
    final_required = frozenset(
        shard.digest for shard in final_graph.shards if shard.name in closure
    )
    return find_member_evidence(
        _receipt_root(member),
        tip=tip,
        schema_digest=manifest.signetum.evidence_schema_digest,
        member_identity=member_identity,
        final_graph_digest=final_graph.digest,
        required_digests=required,
        member_environment=member_environment(member, base, tip),
        inputs=inputs,
        expected_selection=selection if manifest.impact.provider is not None else None,
        final_required_digests=final_required,
    )


def _stable_patch_id(repository: Path, base: str, source: str) -> str:
    git = _git_executable()
    diff = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "diff", "--binary", f"{base}..{source}"),
        check=False,
        capture_output=True,
    )
    if diff.returncode != 0:
        raise AdmissionError(diff.stderr.decode(errors="replace").strip() or "git diff failed")
    identified = subprocess.run(  # nosec B603
        (git, "patch-id", "--stable"),
        input=diff.stdout,
        check=False,
        capture_output=True,
    )
    if identified.returncode != 0:
        raise AdmissionError(
            identified.stderr.decode(errors="replace").strip() or "stable patch-id failed"
        )
    output = identified.stdout.decode().split()
    if not output:
        raise AdmissionError("member has no stable patch identity")
    return output[0]


def _proposal_paths(repository: Path) -> tuple[str, ...]:
    """Find affected proposals, leaving unchanged historical intent untouched."""

    manifest = load_manifest(repository / "signetum.toml")
    base = _recorded_base(repository)
    changed = _git(
        repository,
        "diff",
        "--name-only",
        "--diff-filter=ACMRT",
        "-z",
        base,
        "HEAD",
        "--",
        manifest.repository.decisions,
    )
    paths: list[str] = []
    for line in changed.split("\0"):
        if not line or not Path(line).match("*ADP-*.md"):
            continue
        candidate = repository / line
        try:
            head = candidate.read_text(encoding="utf-8")[:512]
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"^Status:\s*Proposed\s*$", head, re.MULTILINE):
            paths.append(line)
    return tuple(paths)


def _require_numbering_base(repository: Path, base: str | None, tip: str) -> None:
    if base is None:
        return
    messages = _git(repository, "log", "--first-parent", "--format=%B%x00", f"{base}..{tip}")
    numbering_bases = re.findall(r"^Signetum-Decision-Base:\s*(\S+)$", messages, re.MULTILINE)
    if numbering_bases and set(numbering_bases) != {base}:
        raise AdmissionError("decision numbering is bound to a different delivery base")


def admit(batch: Path, members: tuple[Path, ...]) -> dict[str, object]:
    """Admit named members into one batch, exclusively."""

    with _exclusive_batch(batch):
        return _admit_held(batch, members)


def _admit_held(batch: Path, members: tuple[Path, ...]) -> dict[str, object]:
    _require_no_merge(batch)
    _require_clean(batch)
    batch_branch = _branch(batch)
    record = read_record(_state_root(batch), batch_branch)
    if record.kind != "batch":
        raise AdmissionError(f"refusing batch admission outside a batch workspace: {batch_branch}")
    admitted: list[dict[str, object]] = []
    unchanged: list[dict[str, str]] = []
    for raw_member in members:
        member = raw_member.resolve()
        if member == batch:
            raise AdmissionError("batch cannot admit itself")
        _require_clean(member)
        member_branch = _branch(member)
        member_tip = _git(member, "rev-parse", "HEAD")
        batch_tip = _git(batch, "rev-parse", "HEAD")
        member_manifest = load_manifest(member / "signetum.toml")
        member_graph, _ = _runtime_validation(member_manifest)
        member_graph.gate("prepare")
        member_graph.gate("batch")
        member_base = _recorded_base(member)
        carried = qualify_member(
            member, member_manifest, member_base, member_tip, operation="admission"
        )
        plans = delivered_plans(member, member_manifest, carried, member_tip)
        record = {"branch": member_branch, "original": member_tip, "worktree": str(member)}
        if _is_ancestor(batch, member_tip, batch_tip):
            unchanged.append(record)
            continue
        batch_base = _recorded_base(batch)
        require_distinct_claims(
            clause_claims(member, member_manifest, member_base, member_tip),
            clause_claims(batch, load_manifest(batch / "signetum.toml"), batch_base, batch_tip),
            incoming_workspace=lambda _, name=member_branch: f"workspace {name}",
            existing_workspace=owning_workspace(batch, f"batch {batch_branch}"),
        )
        ready_evidence = _admission_evidence(member, member_tip, member_manifest)
        patch_id = _stable_patch_id(member, batch_base, member_tip)
        message = "\n".join(
            (
                f"Merge {member_branch} into integration batch",
                "",
                f"Signetum-Base: {batch_base}",
                f"Signetum-Original: {member_tip}",
                f"Signetum-Member: {member_branch}",
                f"Signetum-Batch-Base: {batch_base}",
                f"Signetum-Patch-ID: {patch_id}",
                f"Signetum-Ready-Evidence: {ready_evidence}",
                *(f"Signetum-Plan: {plan}" for plan in plans),
            )
        )
        git = _git_executable()
        completed = subprocess.run(  # nosec B603
            (
                git,
                "-C",
                str(batch),
                "merge",
                "--no-ff",
                member_tip,
                "-m",
                message,
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            diagnostic = completed.stderr.strip() or completed.stdout.strip()
            if _git(batch, "diff", "--name-only", "--diff-filter=U"):
                raise MergeConflict(
                    diagnostic or "batch has an open merge",
                    expected=f"resolve and stage paths, then batch-continue --batch {batch}",
                )
            raise OperationFailed(diagnostic or "batch merge failed")
        admission_commit = _git(batch, "rev-parse", "HEAD")
        admitted.append(
            {
                **record,
                "patch_id": patch_id,
                "ready_evidence": ready_evidence,
                "plan": list(plans),
                "admission_commit": admission_commit,
            }
        )

    if batch_branch == delivery_policy(batch).branch:
        raise AdmissionError("batch source declares its own branch as the delivery target")
    try:
        preparation = worktree_prepare(batch)
    except InfrastructureError as error:
        retry = ["batch-admit", "--batch", str(batch)]
        for member in members:
            retry.extend(("--member", str(member)))
        raise InfrastructureError(str(error), expected=shlex.join(retry)) from error
    source = _git(batch, "rev-parse", "HEAD")
    static = _run_batch_gate(batch, batch_branch, source, preparation["executed"], selector=batch)
    return {
        "schema_version": 1,
        "status": "admitted",
        "admission_base": static.pop("admission_base"),
        "preparation": preparation,
        "static": static,
        "batch": str(batch),
        "batch_branch": batch_branch,
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
        "admitted": admitted,
        "unchanged": unchanged,
    }


def continue_batch(batch: Path) -> dict[str, object]:
    """Complete one batch's pending merge, exclusively."""

    with _exclusive_batch(batch):
        return _continue_batch_held(batch)


def _continue_batch_held(batch: Path) -> dict[str, object]:
    merge_head = repository_path(batch, "rev-parse", "--git-path", "MERGE_HEAD")
    if not merge_head.is_file():
        raise AdmissionError("batch has no merge to continue")
    unmerged = _git(batch, "diff", "--name-only", "--diff-filter=U")
    if unmerged:
        raise AdmissionError(f"unresolved merge paths: {unmerged}")
    staged = _git(batch, "diff", "--cached", "--name-only")
    if not staged:
        raise AdmissionError("batch continuation has no staged resolution")
    preparation = worktree_prepare(batch, allow_merge=True)
    before = _git(batch, "rev-parse", "HEAD")
    staged_tree = _git(batch, "write-tree")
    other = _git(batch, "rev-parse", "MERGE_HEAD")
    against_first = set(_git(batch, "diff", "--name-only", before, staged_tree).splitlines())
    against_second = set(_git(batch, "diff", "--name-only", other, staged_tree).splitlines())
    repaired = tuple(sorted(against_first & against_second))
    resolution = _git(
        batch, "commit-tree", staged_tree, "-p", before, "-p", other, "-m", "batch resolution"
    )
    with _selection_checkout(batch, resolution) as selector:
        static = _run_batch_gate(
            batch,
            _branch(batch),
            resolution,
            preparation["executed"],
            selector=selector,
            recorded_tip=False,
        )
    if _git(batch, "rev-parse", "HEAD") != before or _git(batch, "write-tree") != staged_tree:
        raise ValidationExecutionError("validation changed staged merge identity")
    if run_git(batch, "diff", "--quiet").returncode:
        raise ValidationExecutionError("validation changed merge working files")
    git = _git_executable()
    completed = subprocess.run(  # nosec B603
        (git, "-C", str(batch), "commit", "--no-edit"),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AdmissionError(completed.stderr.strip() or completed.stdout.strip())
    committed = _git(batch, "rev-parse", "HEAD")
    batch_base = _recorded_base(batch)
    if batch_base is None:
        raise AdmissionError("continued admission has no approved batch base")
    record_verified_batch(batch, _branch(batch), committed)
    body = _git(batch, "show", "-s", "--format=%B", committed)
    if re.findall(r"^Signetum-Batch-Sync:\s*(\S+)$", body, re.MULTILINE) == [other]:
        _advance_base(batch, batch_base, other, committed)
    return {
        "schema_version": 1,
        "status": "continued",
        "admission_base": static.pop("admission_base"),
        "preparation": preparation,
        "repaired_paths": list(repaired),
        "static": static,
        "batch": str(batch),
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
        "admission_commit": committed,
    }


def _advance_base(batch: Path, previous: str, delivered: str, tip: str) -> None:
    """Rebind the batch record once committed history attests the merged delivery."""

    if _attested_base(batch, tip) != delivered:
        raise AdmissionError("batch synchronization does not attest the merged delivery tip")
    _delivery_provenance(batch, delivered, tip)
    try:
        advance_batch_base(_state_root(batch), _branch(batch), previous, delivered)
    except WorkspaceError as error:
        raise AdmissionError(str(error)) from error


def sync_batch(batch: Path, source: Path | None = None) -> dict[str, object]:
    """Merge the fresh delivery tip into one open batch, exclusively."""

    if source is not None:
        raise AdmissionError(
            "a batch synchronizes only from the delivery branch",
            expected=f"run maintenance workspace-sync without --batch in {batch}",
        )
    with _exclusive_batch(batch):
        return _sync_batch_held(batch)


def _sync_batch_held(batch: Path) -> dict[str, object]:
    _require_no_merge(batch)
    _require_clean(batch)
    branch = _branch(batch)
    record = read_record(_state_root(batch), branch)
    delivery_branch, delivered = fresh_delivery(batch)
    if record.kind != "batch" or branch == delivery_branch:
        raise AdmissionError("batch synchronization requires an integration batch")
    base = record.base
    tip = _git(batch, "rev-parse", "HEAD")
    attested = _attested_base(batch, tip)
    if attested is not None and attested != base and _is_ancestor(batch, base, attested):
        # A committed synchronization whose record update was interrupted.
        _advance_base(batch, base, attested, tip)
        base = attested
    if attested != base:
        raise AdmissionError("batch provenance does not attest to the recorded base")
    _delivery_provenance(batch, base, tip)
    if not _is_ancestor(batch, base, delivered):
        raise AdmissionError(
            f"delivery tip {delivered} does not descend from the batch base {base}",
            expected="inspect the delivery branch history; a batch never takes rewritten history",
        )
    result: dict[str, object] = {
        "schema_version": 1,
        "batch": str(batch),
        "batch_branch": branch,
        "previous_base": base,
        "base": delivered,
    }
    if delivered == base:
        if verified_batch_tip(batch, branch, base) == tip:
            return {**result, "status": "unchanged", "batch_commit": tip}
    else:
        manifest = load_manifest(batch / "signetum.toml")
        require_distinct_claims(
            clause_claims(batch, manifest, base, tip),
            clause_claims(batch, manifest, base, delivered),
            incoming_workspace=owning_workspace(batch, f"batch {branch}"),
            existing_workspace=owning_workspace(batch, f"{delivery_branch} at {delivered}"),
        )
        message = "\n".join(
            (
                f"Merge {delivery_branch} into {branch}",
                "",
                f"Signetum-Batch-Sync: {delivered}",
                f"Signetum-Batch-Base: {delivered}",
                f"Signetum-Previous-Batch-Base: {base}",
            )
        )
        if _is_ancestor(batch, delivered, tip):
            # A member already synchronized this tip; record the base move as a merge.
            merged = _git(
                batch, "commit-tree", f"{tip}^{{tree}}", "-p", tip, "-p", delivered, "-m", message
            )
            command: tuple[str, ...] = ("merge", "--ff-only", merged)
        else:
            command = ("merge", "--no-ff", delivered, "-m", message)
        completed = subprocess.run(  # nosec B603
            (_git_executable(), "-C", str(batch), *command),
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            diagnostic = completed.stderr.strip() or completed.stdout.strip()
            if _git(batch, "diff", "--name-only", "--diff-filter=U"):
                raise MergeConflict(
                    diagnostic or "batch synchronization has an open merge",
                    expected=f"resolve and stage paths, then batch-continue --batch {batch}",
                )
            raise OperationFailed(diagnostic or "batch synchronization merge failed")
        tip = _git(batch, "rev-parse", "HEAD")
        _advance_base(batch, base, delivered, tip)
    try:
        preparation = worktree_prepare(batch)
    except InfrastructureError as error:
        retry = ["maintenance", "workspace-sync"]
        raise InfrastructureError(
            str(error), expected=f"run {shlex.join(retry)} in {batch} again"
        ) from error
    static = _run_batch_gate(batch, branch, tip, preparation["executed"], selector=batch)
    return {
        **result,
        "status": "synchronized",
        "admission_base": static.pop("admission_base"),
        "preparation": preparation,
        "static": static,
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
    }


def _admission_paths(batch: Path, before: str, source: str) -> tuple[str, ...]:
    changed = _git(batch, "diff", "--name-only", "-z", "--no-renames", before, source)
    return tuple(sorted(path for path in changed.split("\0") if path))


@contextmanager
def _selection_checkout(batch: Path, resolution: str) -> Iterator[Path]:
    """Give a provider the exact resolved merge as a clean detached checkout.

    A conflict resolution is staged, not committed, so only a temporary checkout
    of its synthetic merge can be the committed source a provider requires.
    Without a provider, selection reads only paths and needs no checkout.
    """

    if load_manifest(batch / "signetum.toml").impact.provider is None:
        yield batch
        return
    parent = Path(tempfile.mkdtemp(prefix="signetum-selection-"))
    execution = parent / "tree"
    try:
        _git(batch, "worktree", "add", "--detach", str(execution), resolution)
        graph, _ = _runtime_validation(load_manifest(execution / "signetum.toml"))
        if any(gate.name == "prepare" for gate in graph.gates):
            worktree_prepare(execution)
        yield execution
    finally:
        removal_error = _drop_qualification(parent, batch)
    if removal_error is not None:
        raise InfrastructureError(
            f"selection worktree could not be removed: {parent}"
        ) from removal_error


def _batch_graph(
    batch: Path, selector: Path, before: str, source: str, prepared: frozenset[str]
) -> ValidationGraph:
    """Resolve the batch gate against what the admitted increment selects.

    The increment runs from the last batch tip whose gate passed to the new tip.
    Refuse before any batch check runs when the declared batch gate does not
    cover the member shards that increment selects.
    """

    manifest = load_manifest(selector / "signetum.toml")
    files = _admission_paths(batch, before, source)
    if not files:
        return _runtime_validation(manifest)[0]
    resolved = select_repository(selector, manifest, files, base=before, source=source)
    required, _ = _member_shards(resolved.manifest, resolved.selection, member_closure=False)
    graph, _ = _runtime_validation(resolved.manifest, member_shards=required)
    executed = graph.execution_order("batch")
    covered = set(executed) | graph.covered(executed)
    missing = [
        shard.name
        for shard in graph.shards
        if shard.name in graph.execution_order("member")
        and shard.name not in covered
        and shard.digest not in prepared
    ]
    if missing:
        raise AdmissionError(
            "batch gate does not run the shards its admission selects: " + ", ".join(missing),
            expected="declare them in the batch gate, commit that, and rerun the batch operation",
        )
    return graph


def _run_batch_gate(
    batch: Path,
    branch: str,
    source: str,
    prepared_names: list[str],
    *,
    selector: Path,
    recorded_tip: bool = True,
) -> dict[str, object]:
    base = _recorded_base(batch)
    if base is None:
        raise AdmissionError("batch has no recorded base")
    declared, _ = _runtime_validation(load_manifest(batch / "signetum.toml"))
    prepared = frozenset(shard.digest for shard in declared.shards if shard.name in prepared_names)
    before = verified_batch_tip(batch, branch, base)
    graph = _batch_graph(batch, selector, before, source, prepared)
    owed = require_accounted(batch, branch, base, graph.execution_order("batch"))
    try:
        static = run_diagnostic_gate(
            batch,
            graph,
            "batch",
            executed=set(prepared),
            advisory_world=True,
            remembered=owed,
            admission_base=before,
        )
    except ValidationExecutionError as error:
        remember_failure(
            batch,
            branch,
            gate="batch",
            base=base,
            tip=_git(batch, "rev-parse", "HEAD"),
            error=error,
            owed=owed,
        )
        raise
    forget_failures(batch, branch)
    if recorded_tip:
        record_verified_batch(batch, branch, source)
    return {**static, "admission_base": before}


def batch_open(
    repository: Path, members: tuple[Path, ...], name: str | None = None
) -> dict[str, object]:
    if not members:
        raise AdmissionError("batch-open requires explicitly named members")
    member_names = tuple(_branch(member.resolve()) for member in members)
    task = (
        name
        if name is not None
        else "-and-".join(branch.split("/", 1)[-1].replace("/", "-") for branch in member_names)
    )
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,95}", task) is None:
        raise AdmissionError(
            "batch name requires a lowercase task slug of at most 96 characters; use --name"
        )
    _, approved_base = fresh_delivery(repository)
    branch = f"batch/{task}"
    opened = open_workspace(
        repository,
        branch,
        approved_base,
        kind="batch",
        members=member_names,
    )
    batch = Path(str(opened["worktree"]))
    result = admit(batch, members)
    return {**result, "status": "opened", "worktree": str(batch)}


def _require_worktree_directory(path: Path, role: str) -> None:
    if not path.is_dir():
        raise AdmissionError(
            f"{role} must be an existing worktree directory; a branch name is not a path: {path}"
        )


def batch_deliver(
    source: Path, target: Path, expected_base: str, expected_tip: str
) -> dict[str, object]:
    _require_worktree_directory(source, "source")
    _require_worktree_directory(target, "target")
    _require_clean(source)
    _require_clean(target)
    if _git(source, "rev-parse", "HEAD") != expected_tip:
        raise AdmissionError("source tip differs from expected batch tip")
    recorded_base = _recorded_base(source)
    if recorded_base != expected_base:
        raise AdmissionError("recorded batch base differs from expected base")
    if _attested_base(source, expected_tip) != recorded_base:
        raise AdmissionError("batch provenance does not attest to the recorded base")
    final_receipts = sorted(_receipt_root(source).glob("final-*.json"))
    if not final_receipts:
        raise AdmissionError("no final receipt exists")
    matching_receipt = next(
        (
            path
            for path in final_receipts
            if (payload := json.loads(path.read_text(encoding="utf-8"))).get("source")
            == expected_tip
            and payload.get("base") == expected_base
            and payload.get("valid") is True
        ),
        None,
    )
    if matching_receipt is None:
        raise AdmissionError("final receipt does not bind the expected batch tip")

    payload = json.loads(matching_receipt.read_text(encoding="utf-8"))
    review = payload.get("delivery_review")
    try:
        current_inputs = execution_review_inputs(
            source,
            load_manifest(source / "signetum.toml"),
            expected_base,
            expected_tip,
            _receipt_root(source),
        )
    except (DeviationError, DevelopmentReviewError) as error:
        raise AdmissionError(f"delivery review inputs changed: {error}") from error
    if not isinstance(review, dict) or review.get("inputs") != current_inputs:
        raise AdmissionError("delivery review inputs changed or are absent; rerun final")

    target_branch = _branch(target)
    if target_branch != delivery_policy(source).branch:
        raise AdmissionError("target branch is not the repository-declared delivery branch")
    members, plans = _delivery_provenance(source, expected_base, expected_tip)
    publication = publish_batch(
        source,
        target,
        expected_base,
        expected_tip,
        target_branch,
        git=_git,
        remote_tip=_remote_branch_tip,
        is_ancestor=_is_ancestor,
    )
    removed_worktrees, retained_worktrees = _cleanup_delivered_worktrees(target, source, members)
    return {
        "schema_version": 1,
        "status": "delivered",
        "base": expected_base,
        "source": expected_tip,
        "target": str(target),
        "target_branch": target_branch,
        "delivery_commit": publication.commit,
        "remote": publication.remote,
        "members": members,
        "plans": plans,
        "validation": {"final_receipt": str(matching_receipt), "source": expected_tip},
        "removed_worktrees": removed_worktrees,
        "retained_worktrees": retained_worktrees,
    }


def _remote_branch_tip(repository: Path, branch: str) -> str:
    git = _git_executable()
    completed = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "ls-remote", "--heads", "origin", branch),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AdmissionError(completed.stderr.strip() or "remote branch lookup failed")
    lines = tuple(line for line in completed.stdout.splitlines() if line.strip())
    if len(lines) != 1:
        raise AdmissionError(f"remote branch identity is not unique: {branch}")
    return lines[0].split()[0]


def _git_executable() -> str:
    executable = which("git")
    if executable is None:
        raise GitInfrastructureError("Git executable is unavailable")
    return executable


def _parser() -> argparse.ArgumentParser:
    parser = OperationParser(prog="lifecycle")
    commands = parser.add_subparsers(dest="command", required=True)
    workspace = commands.add_parser("workspace-open")
    workspace.add_argument("branch")
    workspace.add_argument("base")
    diagnostic = commands.add_parser("changed")
    diagnostic.add_argument("--explain", action="store_true")
    commands.add_parser("ready")
    opening = commands.add_parser("batch-open")
    opening.add_argument("--name")
    opening.add_argument("--member", type=Path, action="append", required=True)
    admission = commands.add_parser("batch-admit")
    admission.add_argument("--batch", type=Path, required=True)
    admission.add_argument("--member", type=Path, action="append", required=True)
    continuation = commands.add_parser("batch-continue")
    continuation.add_argument("--batch", type=Path, required=True)
    commands.add_parser("final")
    delivery = commands.add_parser(
        "batch-deliver",
        help="Publish a reviewed batch. Source and target are existing worktree directories.",
    )
    delivery.add_argument(
        "source",
        type=Path,
        help="Existing batch worktree directory. A branch name is not a path.",
    )
    delivery.add_argument(
        "target",
        type=Path,
        help="Existing delivery worktree directory. A branch name is not a path.",
    )
    delivery.add_argument("expected_base", help="Full commit of the expected batch base.")
    delivery.add_argument("expected_batch_tip", help="Full commit of the reviewed batch tip.")
    return parser


def _dispatch(repository: Path, supplied: list[str]) -> dict[str, object]:
    parsed = _parser().parse_args(supplied)
    result: dict[str, object]
    if parsed.command == "workspace-open":
        result = workspace_open(repository, parsed.branch, parsed.base)
    elif parsed.command == "changed":
        result = changed(repository, parsed.explain)
    elif parsed.command == "ready":
        result = validate(repository, "member")
    elif parsed.command == "batch-open":
        result = batch_open(repository, tuple(parsed.member), parsed.name)
    elif parsed.command == "batch-admit":
        result = admit(parsed.batch.resolve(), tuple(parsed.member))
    elif parsed.command == "batch-continue":
        result = continue_batch(parsed.batch.resolve())
    elif parsed.command == "final":
        result = validate(repository, "final")
    else:
        result = batch_deliver(
            parsed.source.resolve(),
            parsed.target.resolve(),
            parsed.expected_base,
            parsed.expected_batch_tip,
        )
    return result


def main(arguments: list[str] | None = None) -> int:
    supplied = sys.argv[1:] if arguments is None else arguments
    operation = supplied[0] if supplied else "lifecycle"
    repository = Path.cwd().resolve()
    return run_operation(
        repository, operation, lambda: _dispatch(repository, supplied), state_root=_state_root
    )


if __name__ == "__main__":
    sys.exit(main())
