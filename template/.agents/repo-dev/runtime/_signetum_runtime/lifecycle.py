# Generated from signetum.lifecycle; edit the engine source and regenerate.
"""Lifecycle authority for explicit Signetum batch admission."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess  # nosec B404 -- fixed tuple commands, never a shell
import sys
from dataclasses import replace
from pathlib import Path
from shutil import which

from .admission import find_member_evidence
from .change_member import qualify_member
from .change_scope import (
    delivered_plans,
)
from .configuration import member_shards as _member_shards
from .delivery import publish_batch
from .development_store import DevelopmentReviewError
from .deviations import (
    DeviationError,
)
from .evidence_receipts import ValidationSelection
from .execution import (
    ValidationExecutionError,
    build_evidence_identity,
    execute_gate,
)
from .execution_review import execution_review_inputs
from .git import GitError, GitInfrastructureError, git_output, run_git
from .impact import select_paths
from .lifecycle_validation import validate_workspace
from .manifest import RepositoryManifest, load_manifest
from .operation_cli import OperationParser, run_operation
from .operations import (
    AdmissionError,
    InfrastructureError,
    MergeConflict,
    OperationFailed,
)
from .policy import delivery_policy
from .provenance import attested_base as _attested_base
from .provenance import members_and_plans as _delivery_provenance
from .ratchet import ratchet_baseline
from .repository import (
    RepositoryValidationAdapter,
    run_diagnostic_gate,
)
from .repository import configured_validation as _runtime_validation
from .synchronization import member_contribution_paths
from .workspace_operations import cleanup_delivered as _cleanup_delivered_worktrees
from .workspace_operations import (
    fresh_delivery,
    open_workspace,
    workspace_open,
    worktree_prepare,
)
from .workspaces import (
    branch_name as _branch,
)
from .workspaces import (
    exclusive_batch as _exclusive_batch,
)
from .workspaces import (
    read_record,
)
from .workspaces import (
    recorded_base as _recorded_base,
)
from .workspaces import (
    require_clean as _require_clean,
)
from .workspaces import (
    require_no_merge as _require_no_merge,
)
from .workspaces import (
    state_root as _state_root,
)


def _receipt_root(repository: Path) -> Path:
    root = _state_root(repository) / "validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _selection(repository: Path, base: str, manifest: RepositoryManifest) -> ValidationSelection:
    files = member_contribution_paths(repository, base, _git(repository, "rev-parse", "HEAD"))
    return select_paths(files, manifest.impact.rules)


def changed(repository: Path, explain: bool, *, validate_only: bool = False) -> dict[str, object]:
    _require_clean(repository)
    base = _recorded_base(repository)
    source = _git(repository, "rev-parse", "HEAD")
    manifest = load_manifest(repository / "signetum.toml")
    files = member_contribution_paths(repository, base, source)
    selected = select_paths(files, manifest.impact.rules)
    if not files:
        raise AdmissionError("workspace has no committed contribution to validate")
    member_shards, deferred = _member_shards(manifest, selected, member_closure=False)
    graph, inputs = _runtime_validation(manifest, member_shards=member_shards)
    checks = (
        {"executed": []}
        if validate_only
        else run_diagnostic_gate(repository, graph, "member", member_base=base, tools=inputs.tools)
    )
    if _git(repository, "rev-parse", "HEAD") != source:
        raise ValidationExecutionError("diagnostic changed the committed source")
    try:
        _require_clean(repository)
    except AdmissionError as error:
        raise ValidationExecutionError("diagnostic changed working files") from error
    return {
        "schema_version": 1,
        "status": "selection-only"
        if validate_only
        else ("changed" if checks["executed"] else "nothing-selected"),
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
        "executed": checks["executed"],
        "checks_started": bool(checks["executed"]),
        "shard_details": checks.get("shard_details", {}),
        "recovered_flake_defects": checks.get("recovered_flake_defects", []),
        "deferred_world_shards": deferred,
    }


def validate(repository: Path, kind: str) -> dict[str, object]:
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
        base = _recorded_base(repository)
        numbered = _number_proposals(repository, base)
        result = _validate_held(repository, kind)
        return {**result, "numbered": numbered}


def _validate_held(repository: Path, kind: str) -> dict[str, object]:
    return validate_workspace(
        repository,
        kind,
        configure=_runtime_validation,
        adapter_factory=RepositoryValidationAdapter,
        receipt_root=_receipt_root,
        proposal_paths=_proposal_paths,
        check_numbering_base=_require_numbering_base,
        execute=execute_gate,
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
    selection = _selection(member, base, manifest)
    required_names, _ = _member_shards(manifest, selection)
    graph, inputs = _runtime_validation(manifest, member_shards=required_names)
    closure = set(graph.execution_order("member"))
    required = frozenset(shard.digest for shard in graph.shards if shard.name in closure)
    ratchets = tuple(
        shard.name for shard in graph.shards if shard.name in closure and shard.ratchet_command
    )
    qualified_base = ratchet_baseline(member, base, tip) if ratchets else base
    adapter = RepositoryValidationAdapter(member)
    member_identity = build_evidence_identity(graph, replace(inputs, base=base), adapter)
    final_graph, _ = _runtime_validation(manifest)
    return find_member_evidence(
        _receipt_root(member),
        tip=tip,
        schema_digest=manifest.signetum.evidence_schema_digest,
        member_identity=member_identity,
        final_graph_digest=final_graph.digest,
        required_digests=required,
        ratchet_baselines={name: qualified_base for name in ratchets},
        inputs=inputs,
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
    """Return every decision still declaring itself a proposal.

    A proposal is identified by its declared status, not by its file name: an
    accepted decision may stay unnumbered, so a name alone cannot say whether
    one is still awaiting acceptance.
    """

    paths: list[str] = []
    for line in _git(repository, "ls-files", "*ADP-*.md").splitlines():
        if not line:
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


def _record_supersession(batch: Path, formal_path: Path) -> None:
    """Write the reciprocal entry into every decision this one replaces.

    A supersession only the successor records leaves every reader of the
    replaced decision believing it still stands.
    """

    decision = batch / formal_path
    declared = re.search(
        r"^Supersedes:\s*(.+)$", decision.read_text(encoding="utf-8"), re.MULTILINE
    )
    if declared is None:
        return
    for reference in (item.strip() for item in declared.group(1).split(",")):
        if not reference or reference.lower() == "none":
            continue
        target = decision.parent / Path(reference).name
        if not target.is_file():
            raise AdmissionError(f"decision supersedes an absent decision: {reference}")
        content = target.read_text(encoding="utf-8")
        edge = re.search(r"^Superseded by:(.*)$", content, re.MULTILINE)
        if edge is None:
            raise AdmissionError(f"decision declares no supersession field: {reference}")
        successors = tuple(
            value.strip()
            for value in edge.group(1).split(",")
            if value.strip() and value.strip().lower() != "none"
        )
        successors = tuple(dict.fromkeys((*successors, formal_path.name)))
        updated = (
            content[: edge.start()]
            + "Superseded by: "
            + ", ".join(successors)
            + content[edge.end() :]
        )
        target.write_text(updated, encoding="utf-8")


def _number_proposals(batch: Path, base: str) -> list[dict[str, str]]:
    manifest = load_manifest(batch / "signetum.toml")
    directory = manifest.repository.decisions.rstrip("/")
    base_names = _git(batch, "ls-tree", "-r", "--name-only", base).splitlines()
    proposals = tuple(
        path
        for path in _git(batch, "ls-files", f"{directory}/ADP-*.md").splitlines()
        if not re.fullmatch(r"ADP-\d{4}-.+\.md", Path(path).name)
        and re.search(
            r"^Status:\s*Accepted\s*$",
            (batch / path).read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        and not (
            path in base_names
            and re.search(
                r"^Status:\s*Accepted\s*$",
                _git(batch, "show", f"{base}:{path}"),
                re.MULTILINE,
            )
        )
    )
    if not proposals:
        return []
    _, remote_tip = fresh_delivery(batch)
    remote_names = _git(batch, "ls-tree", "-r", "--name-only", remote_tip).splitlines()
    used = [
        int(match.group(1))
        for path in (*base_names, *remote_names, *_git(batch, "ls-files").splitlines())
        if path.startswith(directory + "/")
        if (match := re.search(r"(?:^|/)ADP-(\d{4})-[^/]+\.md$", path))
    ]
    next_number = max(used, default=0) + 1
    rewrites: list[dict[str, str]] = []
    for proposal in sorted(proposals):
        proposal_path = Path(proposal)
        slug = proposal_path.name.removeprefix("ADP-")
        formal_path = proposal_path.with_name(f"ADP-{next_number:04d}-{slug}")
        if (batch / formal_path).exists():
            raise AdmissionError(f"formal decision already exists: {formal_path}")
        _git(batch, "mv", proposal, formal_path.as_posix())
        tracked = tuple(filter(None, _git(batch, "ls-files").splitlines()))
        old_name = proposal_path.name
        new_name = formal_path.name
        for relative in tracked:
            candidate = batch / relative
            if not candidate.is_file():
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rewritten = content.replace(proposal, formal_path.as_posix()).replace(
                old_name, new_name
            )
            if rewritten != content:
                candidate.write_text(rewritten, encoding="utf-8")
        _record_supersession(batch, formal_path)
        rewrites.append({"proposal": proposal, "formal": formal_path.as_posix()})
        next_number += 1
    _git(batch, "add", "-u")
    _git(
        batch,
        "commit",
        "-m",
        "signetum: allocate formal decision identities",
        "-m",
        "\n".join(
            (
                f"Signetum-Decision-Base: {base}",
                *(
                    "Signetum-Decision-Rename: " + json.dumps([item["proposal"], item["formal"]])
                    for item in rewrites
                ),
            )
        ),
    )
    return rewrites


def admit(batch: Path, members: tuple[Path, ...]) -> dict[str, object]:
    """Admit named members into one batch, exclusively."""

    with _exclusive_batch(batch):
        return _admit_held(batch, members)


def _admit_held(batch: Path, members: tuple[Path, ...]) -> dict[str, object]:
    _require_no_merge(batch)
    _require_clean(batch)
    batch_branch = _branch(batch)
    record = read_record(_state_root(batch), batch_branch)
    if record.kind != "batch" or batch_branch == delivery_policy(batch).branch:
        raise AdmissionError(f"refusing batch admission outside a batch workspace: {batch_branch}")
    graph, _ = _runtime_validation(load_manifest(batch / "signetum.toml"))
    graph.gate("prepare")
    graph.gate("batch")

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
        ready_evidence = _admission_evidence(member, member_tip, member_manifest)
        patch_id = _stable_patch_id(member, batch_base, member_tip)
        message = "\n".join(
            (
                f"merge: admit {member_branch}",
                "",
                f"Signetum-Base: {batch_base}",
                f"Signetum-Original: {member_tip}",
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
            merge_head = Path(_git(batch, "rev-parse", "--git-path", "MERGE_HEAD"))
            if not merge_head.is_absolute():
                merge_head = batch / merge_head
            diagnostic = completed.stderr.strip() or completed.stdout.strip()
            if merge_head.is_file():
                raise MergeConflict(
                    diagnostic or "batch has an open merge",
                    expected=f"resolve and stage paths, then batch-continue {batch}",
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

    try:
        preparation = worktree_prepare(batch)
    except InfrastructureError as error:
        retry = ["batch-admit", str(batch)]
        for member in members:
            retry.extend(("--member", str(member)))
        raise InfrastructureError(str(error), expected=shlex.join(retry)) from error
    graph, _ = _runtime_validation(load_manifest(batch / "signetum.toml"))
    executed = {shard.digest for shard in graph.shards if shard.name in preparation["executed"]}
    static = run_diagnostic_gate(batch, graph, "batch", executed=executed, advisory_world=True)
    return {
        "schema_version": 1,
        "status": "admitted",
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
    merge_head = Path(_git(batch, "rev-parse", "--git-path", "MERGE_HEAD"))
    if not merge_head.is_absolute():
        merge_head = batch / merge_head
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
    manifest = load_manifest(batch / "signetum.toml")
    selected = select_paths(repaired, manifest.impact.rules)
    shards, _ = _member_shards(manifest, selected, member_closure=False)
    graph, _ = _runtime_validation(manifest, member_shards=shards)
    executed = {shard.digest for shard in graph.shards if shard.name in preparation["executed"]}
    repaired_checks = run_diagnostic_gate(batch, graph, "member", executed=executed)
    static = run_diagnostic_gate(batch, graph, "batch", executed=executed, advisory_world=True)
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
    return {
        "schema_version": 1,
        "status": "continued",
        "preparation": preparation,
        "repaired_paths": list(repaired),
        "checks": repaired_checks,
        "static": static,
        "batch": str(batch),
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
        "admission_commit": committed,
    }


def batch_open(repository: Path, members: tuple[Path, ...]) -> dict[str, object]:
    if not members:
        raise AdmissionError("batch-open requires explicitly named members")
    _, approved_base = fresh_delivery(repository)
    branch = f"batch/{approved_base}"
    opened = open_workspace(
        repository,
        branch,
        approved_base,
        kind="batch",
        members=tuple(str(member.resolve()) for member in members),
    )
    batch = Path(str(opened["worktree"]))
    result = admit(batch, members)
    return {**result, "status": "opened", "worktree": str(batch)}


def batch_deliver(
    source: Path, target: Path, expected_base: str, expected_tip: str
) -> dict[str, object]:
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
    diagnostic.add_argument("--validate-only", action="store_true")
    commands.add_parser("ready")
    opening = commands.add_parser("batch-open")
    opening.add_argument("--member", type=Path, action="append", required=True)
    admission = commands.add_parser("batch-admit")
    admission.add_argument("--batch", type=Path, required=True)
    admission.add_argument("--member", type=Path, action="append", required=True)
    continuation = commands.add_parser("batch-continue")
    continuation.add_argument("--batch", type=Path, required=True)
    commands.add_parser("final")
    delivery = commands.add_parser("batch-deliver")
    delivery.add_argument("source", type=Path)
    delivery.add_argument("target", type=Path)
    delivery.add_argument("expected_base")
    delivery.add_argument("expected_batch_tip")
    return parser


def _dispatch(repository: Path, supplied: list[str]) -> dict[str, object]:
    parsed = _parser().parse_args(supplied)
    result: dict[str, object]
    if parsed.command == "workspace-open":
        result = workspace_open(repository, parsed.branch, parsed.base)
    elif parsed.command == "changed":
        result = changed(repository, parsed.explain, validate_only=parsed.validate_only)
    elif parsed.command == "ready":
        result = validate(repository, "member")
    elif parsed.command == "batch-open":
        result = batch_open(repository, tuple(parsed.member))
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
