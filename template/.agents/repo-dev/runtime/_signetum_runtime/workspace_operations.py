# Generated from signetum.workspace_operations; edit the engine source and regenerate.
"""Supported workspace preparation, synchronization and residue removal."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Literal

from . import worktrunk as wt
from .git import git_output, run_git
from .manifest import load_manifest, parse_manifest
from .operations import AdmissionError, InfrastructureError, MergeConflict, OperationFailed
from .policy import delivery_policy
from .preparation import PreparationResult, prepare_workspace
from .provenance import attested_base, members_and_plans
from .repository import configured_validation
from .synchronization import authorize_source
from .workspaces import (
    WorkspaceError,
    WorkspaceRecord,
    branch_name,
    exclusive_batch,
    read_record,
    record_path,
    require_clean,
    require_no_merge,
    state_root,
    write_record,
)


def worktree_prepare(repository: Path, *, allow_merge: bool = False) -> PreparationResult:
    return prepare_workspace(
        repository,
        lambda: configured_validation(load_manifest(repository / "signetum.toml"))[0],
        wt.run_tool,
        allow_merge=allow_merge,
    )


def open_workspace(
    repository: Path,
    branch: str,
    base: str,
    *,
    kind: Literal["member", "batch"] = "member",
    members: tuple[str, ...] = (),
) -> dict[str, object]:
    root = Path(git_output(repository, "rev-parse", "--show-toplevel"))
    source = git_output(root, "rev-parse", base)
    if branch == delivery_policy(root).branch:
        raise AdmissionError("workspace-open cannot adopt the delivery worktree")
    registered = tuple(item for item in wt.worktrees(root) if item.branch == branch)
    resumed = bool(registered)
    if registered:
        if len(registered) != 1:
            raise AdmissionError(f"workspace branch is registered more than once: {branch}")
        workspace = registered[0]
        if branch == delivery_policy(workspace.path).branch:
            raise AdmissionError("workspace-open cannot adopt a delivery worktree")
        record_location = record_path(state_root(root), branch)
        if not record_location.exists() and workspace.head == source:
            write_record(
                state_root(root),
                WorkspaceRecord(
                    schema_version=1, branch=branch, base=source, kind=kind, members=members
                ),
            )
        record = read_record(state_root(root), branch)
        if record.base != source or record.kind != kind:
            raise AdmissionError("existing workspace has a different recorded base or role")
    else:
        manifest = parse_manifest(git_output(root, "show", f"{source}:signetum.toml"))
        graph, _ = configured_validation(manifest)
        graph.gate("prepare")
        if kind == "batch":
            graph.gate("batch")
        wt.worktrunk(
            root,
            (
                "switch",
                "--create",
                branch,
                "--base",
                source,
                "--no-hooks",
                "--no-cd",
                "--format=json",
            ),
            json_output=True,
        )
        workspace = wt.registered_workspace(root, branch)
        if workspace.head != source:
            raise AdmissionError("Worktrunk workspace does not match the exact approved base")
        write_record(
            state_root(root),
            WorkspaceRecord(
                schema_version=1, branch=branch, base=source, kind=kind, members=members
            ),
        )
    if kind == "batch" and git_output(workspace.path, "rev-parse", "HEAD") == source:
        git_output(
            workspace.path,
            "commit",
            "--allow-empty",
            "-m",
            "signetum: open provenance batch",
            "-m",
            f"Signetum-Batch-Format: 1\nSignetum-Batch-Base: {source}",
        )
    try:
        preparation = worktree_prepare(workspace.path)
    except InfrastructureError as error:
        if kind == "batch" and members:
            retry = ["batch-admit", str(workspace.path)]
            for member in members:
                retry.extend(("--member", member))
        elif kind == "batch":
            retry = ["maintenance", "worktree-prepare", str(workspace.path)]
        else:
            retry = ["workspace-open", branch, source]
        raise InfrastructureError(str(error), expected=shlex.join(retry)) from error
    return {
        "status": "opened",
        "base": source,
        "branch": branch,
        "worktree": str(workspace.path),
        "source": git_output(workspace.path, "rev-parse", "HEAD"),
        "resumed": resumed,
        "preparation": preparation,
    }


def workspace_open(repository: Path, branch: str, base: str) -> dict[str, object]:
    return open_workspace(repository, branch, base)


def fresh_delivery(repository: Path) -> tuple[str, str]:
    branch = delivery_policy(repository).branch
    git_output(repository, "fetch", "--no-tags", "origin", f"refs/heads/{branch}")
    return branch, git_output(repository, "rev-parse", "FETCH_HEAD")


def _merge_source(repository: Path, source: str, label: str) -> dict[str, object]:
    before = git_output(repository, "rev-parse", "HEAD")
    completed = run_git(
        repository,
        "merge",
        "--no-ff",
        source,
        "-m",
        f"Synchronize {label}\n\nSignetum-Sync: {source}\nSignetum-Sync-Source: {label}",
    )
    if completed.returncode:
        try:
            require_no_merge(repository)
        except MergeConflict as error:
            raise MergeConflict(
                completed.stderr.strip() or completed.stdout.strip(),
                expected="commit the resolved merge, then maintenance worktree-prepare and ready",
            ) from error
        raise OperationFailed(completed.stderr.strip() or completed.stdout.strip())
    return {
        "status": "synchronized",
        "source": source,
        "before": before,
        "tip": git_output(repository, "rev-parse", "HEAD"),
    }


def workspace_sync(repository: Path, batch: Path | None = None) -> dict[str, object]:
    if run_git(repository, "rev-parse", "--verify", "MERGE_HEAD").returncode == 0:
        raise MergeConflict(
            "member has an open merge",
            expected="commit the resolved merge, then maintenance worktree-prepare and ready",
        )
    if _has_git_operation(repository):
        raise AdmissionError("cannot synchronize during another Git operation")
    require_clean(repository)
    record = read_record(state_root(repository), branch_name(repository))
    policy = delivery_policy(repository)
    if record.kind != "member" or record.branch == policy.branch:
        raise AdmissionError("workspace-sync requires an implementation member")
    if batch is None:
        branch, source = fresh_delivery(repository)
        authorize_source(repository, record.base, source, "delivery")
        return _merge_source(repository, source, f"origin/{branch}")
    if state_root(repository) != state_root(batch):
        raise AdmissionError("batch synchronization requires the same repository")
    with exclusive_batch(batch):
        require_no_merge(batch)
        require_clean(batch)
        batch_record = read_record(state_root(batch), branch_name(batch))
        source = git_output(batch, "rev-parse", "HEAD")
        if batch_record.kind != "batch" or attested_base(batch, source) != batch_record.base:
            raise AdmissionError("synchronization source has no verified batch provenance")
        members_and_plans(batch, batch_record.base, source)
        authorize_source(repository, record.base, source, "batch")
        return _merge_source(repository, source, f"batch/{batch_record.branch}")


def _has_git_operation(repository: Path) -> bool:
    for name in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    ):
        path = Path(git_output(repository, "rev-parse", "--git-path", name))
        if not path.is_absolute():
            path = repository / path
        if path.exists():
            return True
    return False


def removal_reason(
    repository: Path,
    workspace: wt.WorkspaceIdentity,
    delivered_tip: str,
    protected: frozenset[Path],
    *,
    expected_tip: str | None = None,
    discard: bool = False,
    require_record: bool = False,
) -> str | None:
    """One eligibility predicate for cleanup and delivery's residue removal."""

    if workspace.path.resolve() in protected:
        return "protected"
    if _has_git_operation(workspace.path):
        return "git_operation"
    head = git_output(workspace.path, "rev-parse", "HEAD")
    if head != workspace.head or (expected_tip is not None and head != expected_tip):
        return "advanced"
    try:
        record = read_record(state_root(repository), workspace.branch)
    except WorkspaceError:
        if require_record:
            return "unregistered"
    else:
        if head == record.base:
            return "fresh_workspace"
    ancestor = run_git(repository, "merge-base", "--is-ancestor", head, delivered_tip)
    if ancestor.returncode == 1:
        return "undelivered"
    if ancestor.returncode:
        raise AdmissionError(ancestor.stderr.strip() or "cannot establish cleanup ancestry")
    if discard:
        staged = run_git(workspace.path, "diff", "--cached", "--quiet")
        if staged.returncode == 1:
            return "staged"
        if staged.returncode:
            raise AdmissionError(staged.stderr.strip() or "cannot establish index identity")
    elif git_output(workspace.path, "status", "--porcelain"):
        return "dirty"
    return None


def remove_workspace(
    repository: Path, workspace: wt.WorkspaceIdentity, *, discard: bool = False
) -> None:
    result = wt.worktrunk(
        repository,
        (
            "remove",
            "--foreground",
            "--no-hooks",
            "--force-delete",
            *(("--force",) if discard else ()),
            str(workspace.path),
            "--format=json",
        ),
        json_output=True,
    )
    if not isinstance(result, dict) or result.get("branch_outcome") != "deleted":
        raise InfrastructureError(
            f"Worktrunk did not complete branch removal: {workspace.branch}",
            expected="inspect retained Worktrunk state before retrying cleanup",
        )


def cleanup(
    repository: Path,
    *,
    worktree: Path | None = None,
    branch: str | None = None,
    all_delivered: bool = False,
    protected_worktrees: tuple[Path, ...] = (),
    discard: bool = False,
) -> dict[str, object]:
    if sum((worktree is not None, branch is not None, all_delivered)) != 1:
        raise AdmissionError("select one worktree, branch, or --all-delivered")
    delivery_branch, published = fresh_delivery(repository)
    inventory = wt.worktrees(repository)
    protected = frozenset(
        (
            *(path.resolve() for path in protected_worktrees),
            *(item.path for item in inventory if item.branch == delivery_branch),
        )
    )
    selected = tuple(
        item
        for item in inventory
        if all_delivered
        or item.branch == branch
        or (worktree is not None and item.path == worktree.resolve())
    )
    if not selected:
        raise AdmissionError("cleanup selector names no registered workspace")
    removed: list[str] = []
    retained: list[dict[str, str]] = []
    for item in selected:
        reason = removal_reason(
            repository, item, published, protected, discard=discard, require_record=all_delivered
        )
        if reason:
            retained.append({"branch": item.branch, "worktree": str(item.path), "reason": reason})
        else:
            remove_workspace(repository, item, discard=discard)
            removed.append(str(item.path))
    return {"status": "cleaned", "remote": published, "removed": removed, "retained": retained}


def batch_discard(batch: Path) -> dict[str, object]:
    branch = branch_name(batch)
    record = read_record(state_root(batch), branch)
    if record.kind != "batch" or branch == delivery_policy(batch).branch:
        raise AdmissionError("batch-discard requires a batch workspace")
    with exclusive_batch(batch):
        require_clean(batch)
        if _has_git_operation(batch):
            raise AdmissionError("cannot discard a batch with an open Git operation")
        _, published = fresh_delivery(batch)
        tip = git_output(batch, "rev-parse", "HEAD")
        git_output(batch, "fetch", "--no-tags", "origin")
        if git_output(
            batch, "for-each-ref", "--format=%(refname)", "--contains", tip, "refs/remotes/origin"
        ):
            raise AdmissionError("cannot discard a published batch")
        if run_git(batch, "merge-base", "--is-ancestor", tip, published).returncode == 0:
            raise AdmissionError("cannot discard a delivered batch")
        workspace = wt.registered_workspace(batch, branch)
        remove_workspace(batch, workspace)
        return {"status": "discarded", "branch": branch, "tip": tip, "worktree": str(batch)}


def cleanup_delivered(
    target: Path, source: Path, members: list[dict[str, str]]
) -> tuple[list[str], list[dict[str, str]]]:
    branch, published = fresh_delivery(target)
    inventory = wt.worktrees(target)
    protected = frozenset(
        (target.resolve(), *(item.path for item in inventory if item.branch == branch))
    )
    selected = {item.branch: item for item in inventory}
    removed: list[str] = []
    retained: list[dict[str, str]] = []
    for member in {row["branch"]: row for row in members}.values():
        item = selected.get(member["branch"])
        if item is None:
            continue
        reason = removal_reason(target, item, published, protected, expected_tip=member["original"])
        if reason:
            retained.append({"branch": item.branch, "worktree": str(item.path), "reason": reason})
        else:
            remove_workspace(target, item)
            removed.append(str(item.path))
    parents = git_output(target, "show", "-s", "--format=%P", "HEAD").split()
    for item in inventory:
        if item.path != source.resolve():
            continue
        expected = parents[1] if len(parents) == 2 else None
        reason = removal_reason(target, item, published, protected, expected_tip=expected)
        if reason:
            retained.append({"branch": item.branch, "worktree": str(item.path), "reason": reason})
        else:
            remove_workspace(target, item)
            removed.append(str(item.path))
    return removed, retained
