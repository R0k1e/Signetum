"""Supported workspace preparation, synchronization and residue removal."""

from __future__ import annotations

import json
import shlex
import sys
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from re import fullmatch
from typing import Literal

from signetum import worktrunk as wt
from signetum.git import git_output, repository_path, run_git
from signetum.manifest import load_manifest, parse_manifest
from signetum.operations import AdmissionError, InfrastructureError, MergeConflict, OperationFailed
from signetum.policy import delivery_policy
from signetum.preparation import PreparationResult, prepare_workspace
from signetum.provenance import attested_base, members_and_plans
from signetum.stacking import branch_tip, is_ancestor, stacked_parent
from signetum.synchronization import authorize_source, incorporated_parent_tip
from signetum.validation.repository import configured_validation
from signetum.workspaces import (
    WorkspaceError,
    WorkspaceRecord,
    branch_checkouts,
    branch_name,
    exclude_workspaces,
    exclusive_batch,
    read_record,
    record_path,
    require_clean,
    require_no_merge,
    retire_record,
    state_root,
    workspace_destination,
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
    source = git_output(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    destination = workspace_destination(root, branch)
    if branch == delivery_policy(root).branch:
        raise AdmissionError("workspace-open cannot adopt the delivery worktree")
    # A member opened on another member's branch is stacked on that member's tip.
    parent = stacked_parent(root, base, delivery_policy(root).branch) if kind == "member" else None
    registered = tuple(item for item in wt.worktrees(root) if item.branch == branch)
    resumed = bool(registered)
    if registered:
        if len(registered) != 1:
            raise AdmissionError(f"workspace branch is registered more than once: {branch}")
        workspace = registered[0]
        if workspace.path.resolve() != destination:
            raise AdmissionError("registered workspace is outside its managed destination")
        if kind == "member" and branch == delivery_policy(workspace.path).branch:
            raise AdmissionError("workspace-open cannot adopt a delivery worktree")
        record_location = record_path(state_root(root), branch)
        if not record_location.exists() and workspace.head == source:
            write_record(
                state_root(root),
                WorkspaceRecord(
                    schema_version=1,
                    branch=branch,
                    base=source,
                    kind=kind,
                    members=members,
                    parent=parent,
                ),
            )
        record = read_record(state_root(root), branch)
        if parent is not None and record.parent == parent:
            # The parent may have advanced since; the recorded base stays.
            source = record.base
        if record.base != source or record.kind != kind or record.parent != parent:
            raise AdmissionError(
                "existing workspace has a different recorded base or role",
                expected=(
                    f"run maintenance workspace-sync in {workspace.path} to take the delivery tip"
                    if kind == "batch" == record.kind
                    else "correct the precondition and retry"
                ),
            )
    else:
        if destination.exists():
            raise AdmissionError("workspace destination already exists")
        exclude_workspaces(root)
        if kind == "member":
            manifest = parse_manifest(git_output(root, "show", f"{source}:signetum.toml"))
            graph, _ = configured_validation(manifest)
            graph.gate("prepare")
        wt.worktrunk(
            root,
            (
                "--config-set",
                "worktree-path=" + json.dumps(str(destination)),
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
        if workspace.path.resolve() != destination:
            raise AdmissionError("Worktrunk created a workspace outside its managed destination")
        if workspace.head != source:
            raise AdmissionError("Worktrunk workspace does not match the exact approved base")
        write_record(
            state_root(root),
            WorkspaceRecord(
                schema_version=1,
                branch=branch,
                base=source,
                kind=kind,
                members=members,
                parent=parent,
            ),
        )
    if state_root(workspace.path) != state_root(root):
        raise AdmissionError("workspace belongs to a different Git common directory")
    if kind == "batch":
        # Admission prepares the actual merged source once, including protocol upgrades.
        preparation = PreparationResult(
            status="pending_admission", worktree=str(workspace.path), executed=[]
        )
    else:
        try:
            preparation = worktree_prepare(workspace.path)
        except InfrastructureError as error:
            retry = ["workspace-open", branch, parent or source]
            raise InfrastructureError(str(error), expected=shlex.join(retry)) from error
    return {
        "status": "opened",
        "base": source,
        **({"parent": parent} if parent is not None else {}),
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
        (
            f"Merge {label} into {branch_name(repository)}\n\n"
            f"Signetum-Sync: {source}\nSignetum-Sync-Source: {label}"
        ),
    )
    if completed.returncode:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        if git_output(repository, "diff", "--name-only", "--diff-filter=U"):
            raise MergeConflict(
                diagnostic, expected="resolve and commit paths, then prepare and validate"
            )
        raise OperationFailed(
            diagnostic,
            expected=(
                "inspect the commit hook or pending merge; "
                "complete its commit, then prepare and validate"
            ),
        )
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
        # A stacked member's upstream is its parent until the parent is delivered.
        parent = branch_tip(repository, record.parent) if record.parent else None
        if parent is not None and not is_ancestor(repository, parent, source):
            return _sync_parent(repository, record, parent)
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


def _sync_parent(repository: Path, record: WorkspaceRecord, source: str) -> dict[str, object]:
    """Merge the parent member's current tip; never rebase or rewrite the member."""

    tip = git_output(repository, "rev-parse", "HEAD")
    if is_ancestor(repository, source, tip):
        return {"status": "unchanged", "source": source, "tip": tip}
    held = incorporated_parent_tip(repository, record.base, tip)
    if not is_ancestor(repository, held, source):
        raise AdmissionError(
            f"parent {record.parent} tip {source} does not descend from the parent tip {held} "
            "this member holds; a member never takes rewritten history"
        )
    authorize_source(repository, record.base, source, "parent")
    return _merge_source(repository, source, f"parent/{record.parent}")


def _has_git_operation(repository: Path) -> bool:
    for name in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    ):
        if repository_path(repository, "rev-parse", "--git-path", name).exists():
            return True
    return False


def _paths(repository: Path, *arguments: str) -> set[str]:
    output = git_output(repository, "diff", "--name-only", "--no-renames", "-z", *arguments)
    return {path for path in output.split("\0") if path}


def _merge_adds_content(repository: Path, merge: str) -> bool:
    # A dense combined diff omits every hunk that takes one parent's version,
    # so only a resolution or edit of the merge's own remains.
    return bool(git_output(repository, "diff-tree", "--no-commit-id", "--cc", merge))


def content_proof(repository: Path, head: str, delivered: str) -> dict[str, object] | None:
    """Prove with Git alone that a tip's content is already in the delivery branch."""

    ancestor = run_git(repository, "merge-base", "--is-ancestor", head, delivered)
    if ancestor.returncode == 0:
        return {"outcome": "delivered", "delivery": delivered}
    if ancestor.returncode != 1:
        raise AdmissionError(ancestor.stderr.strip() or "cannot establish cleanup ancestry")
    marks = git_output(
        repository,
        "rev-list",
        "--cherry-mark",
        "--right-only",
        "--no-merges",
        f"{delivered}...{head}",
    ).splitlines()
    merges = git_output(repository, "rev-list", "--merges", f"{delivered}..{head}").splitlines()
    # Each line is a mark followed by the commit: "=" names a patch-equivalent commit.
    if all(mark.startswith("=") for mark in marks) and not any(
        _merge_adds_content(repository, merge) for merge in merges
    ):
        commits = sorted(mark[1:].strip() for mark in marks)
        return {"outcome": "contained", "delivery": delivered, "proof": "patch", "commits": commits}
    base = run_git(repository, "merge-base", head, delivered)
    if base.returncode == 0:
        changed = _paths(repository, base.stdout.strip(), head)
        if not changed & _paths(repository, head, delivered):
            paths = sorted(changed)
            return {"outcome": "contained", "delivery": delivered, "proof": "tree", "paths": paths}
    return None


def _runtime_reason(workspace: wt.WorkspaceIdentity) -> str | None:
    path = workspace.path.resolve()
    runtime_paths = (Path.cwd(), Path(__file__), Path(sys.executable), Path(sys.prefix))
    if any(location.absolute().is_relative_to(path) for location in runtime_paths):
        return "active_runtime"
    return None


def _state_reason(workspace: wt.WorkspaceIdentity, expected_tip: str | None) -> str | None:
    if _has_git_operation(workspace.path):
        return "git_operation"
    head = git_output(workspace.path, "rev-parse", "HEAD")
    if head != workspace.head or (expected_tip is not None and head != expected_tip):
        return "advanced"
    return None


def _clean_reason(workspace: wt.WorkspaceIdentity, discard: bool) -> str | None:
    if discard:
        staged = run_git(workspace.path, "diff", "--cached", "--quiet")
        if staged.returncode == 1:
            return "staged"
        if staged.returncode:
            raise AdmissionError(staged.stderr.strip() or "cannot establish index identity")
    elif git_output(workspace.path, "status", "--porcelain"):
        return "dirty"
    return None


def _record(repository: Path, branch: str) -> WorkspaceRecord | None:
    try:
        return read_record(state_root(repository), branch)
    except WorkspaceError:
        return None


def workspace_ending(
    repository: Path,
    workspace: wt.WorkspaceIdentity,
    delivered_tip: str,
    *,
    expected_tip: str | None = None,
    discard: bool = False,
    require_record: bool = False,
) -> dict[str, object]:
    """The outcome a workspace proves now, or the reason it must stay."""

    reason = _state_reason(workspace, expected_tip)
    if reason:
        return {"reason": reason}
    record = _record(repository, workspace.branch)
    if record is None and require_record:
        return {"reason": "unregistered"}
    if record is not None and workspace.head == record.base:
        return {"reason": "fresh_workspace"}
    proof = content_proof(repository, workspace.head, delivered_tip)
    if proof is None:
        return {"reason": "not_contained"}
    reason = _clean_reason(workspace, discard)
    return {"reason": reason} if reason else proof


def removal(
    repository: Path,
    workspace: wt.WorkspaceIdentity,
    delivered_tip: str,
    protected: frozenset[Path],
    *,
    expected_tip: str | None = None,
    discard: bool = False,
    require_record: bool = False,
) -> dict[str, object]:
    """One eligibility predicate for cleanup and delivery's residue removal."""

    if workspace.path.resolve() in protected:
        return {"reason": "protected"}
    reason = _runtime_reason(workspace)
    if reason:
        return {"reason": reason}
    return workspace_ending(
        repository,
        workspace,
        delivered_tip,
        expected_tip=expected_tip,
        discard=discard,
        require_record=require_record,
    )


def remove_workspace(
    repository: Path,
    workspace: wt.WorkspaceIdentity,
    ending: dict[str, object],
    *,
    discard: bool = False,
) -> dict[str, object]:
    registry = state_root(repository)
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
    wt.require_removed_workspace(result, workspace)
    retired = retire_record(registry, workspace.branch, workspace.head, ending)
    return {
        "branch": workspace.branch,
        "worktree": str(workspace.path),
        "tip": workspace.head,
        **ending,
        "retirement": str(retired),
    }


def _settle(
    repository: Path,
    item: wt.WorkspaceIdentity,
    ending: dict[str, object],
    removed: list[dict[str, object]],
    retained: list[dict[str, str]],
    *,
    discard: bool = False,
) -> None:
    reason = ending.get("reason")
    if isinstance(reason, str):
        retained.append({"branch": item.branch, "worktree": str(item.path), "reason": reason})
    else:
        removed.append(remove_workspace(repository, item, ending, discard=discard))


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
    if discard and all_delivered:
        raise AdmissionError("--discard requires one selected worktree or branch")
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
        if (all_delivered and item.branch != delivery_branch)
        or item.branch == branch
        or (worktree is not None and item.path == worktree.resolve())
    )
    if not selected:
        raise AdmissionError("cleanup selector names no registered workspace")
    removed: list[dict[str, object]] = []
    retained: list[dict[str, str]] = []
    for item in selected:
        ending = removal(
            repository, item, published, protected, discard=discard, require_record=all_delivered
        )
        _settle(repository, item, ending, removed, retained, discard=discard)
    return {"status": "cleaned", "remote": published, "removed": removed, "retained": retained}


_COMMIT = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"


def workspace_abandon(
    repository: Path,
    worktree: Path,
    expected_tip: str,
    *,
    actor: str,
    source: str,
    reason: str,
    discard: bool = False,
) -> dict[str, object]:
    """Remove undelivered work only with the owner's confirmation of its exact tip."""

    for value, name in ((actor, "--actor"), (source, "--source"), (reason, "--reason")):
        if not value.strip():
            raise AdmissionError(f"workspace-abandon requires the owner's {name}")
    if fullmatch(_COMMIT, expected_tip) is None:
        raise AdmissionError("workspace-abandon requires the confirmed tip as a full commit")
    delivery_branch, published = fresh_delivery(repository)
    matches = tuple(item for item in wt.worktrees(repository) if item.path == worktree.resolve())
    if len(matches) != 1:
        raise AdmissionError("workspace-abandon names no registered workspace")
    item = matches[0]
    if item.branch == delivery_branch:
        raise AdmissionError("workspace-abandon cannot remove the delivery checkout")
    record = _record(repository, item.branch)
    with exclusive_batch(item.path) if record and record.kind == "batch" else nullcontext():
        refusal = _runtime_reason(item) or _state_reason(item, expected_tip)
        if refusal == "advanced":
            raise AdmissionError(
                "workspace tip differs from the confirmed tip; confirm the current tip again"
            )
        if refusal:
            raise AdmissionError(f"workspace-abandon refuses {refusal} workspace")
        if record is None or item.head != record.base:
            proof = content_proof(repository, item.head, published)
            if proof is not None:
                raise AdmissionError(
                    f"workspace proves {proof['outcome']}; use maintenance cleanup",
                    expected=f"maintenance cleanup --worktree {shlex.quote(str(item.path))}",
                )
        refusal = _clean_reason(item, discard)
        if refusal:
            raise AdmissionError(
                f"workspace-abandon refuses {refusal} workspace",
                expected="commit or discard the changes; --discard never discards staged work",
            )
        ending: dict[str, object] = {
            "outcome": "abandoned",
            "delivery": published,
            "reason": reason,
            "authorization": {
                "actor": actor,
                "source": source,
                "recorded_at": datetime.now(UTC).date().isoformat(),
            },
        }
        removed = remove_workspace(repository, item, ending, discard=discard)
    return {"status": "abandoned", **removed}


def workspace_endings(repository: Path) -> list[dict[str, object]]:
    """List branch checkouts with the outcome each proves against the last fetched branch."""

    if not (repository / "signetum.toml").is_file():
        # Without a delivery binding there is no branch to prove an outcome against.
        return []
    branch = delivery_policy(repository).branch
    delivered = next(
        (
            completed.stdout.strip()
            for name in (f"refs/remotes/origin/{branch}", f"refs/heads/{branch}")
            if (
                completed := run_git(repository, "rev-parse", "--verify", "--quiet", name)
            ).returncode
            == 0
        ),
        None,
    )
    rows: list[dict[str, object]] = []
    for name, path, head in branch_checkouts(repository):
        if name == branch:
            continue
        # The offline listing has no change state; the ending reads it from Git.
        item = wt.WorkspaceIdentity(name, path, head, dirty=False)
        record = _record(repository, name)
        if not path.is_dir():
            ending: dict[str, object] = {"reason": "missing_checkout"}
        elif delivered is None:
            ending = {"reason": "delivery_branch_unavailable"}
        else:
            ending = workspace_ending(repository, item, delivered, require_record=True)
        rows.append(
            {
                "branch": item.branch,
                "worktree": str(item.path),
                "kind": record.kind if record else None,
                "outcome": ending.get("outcome"),
                "reason": ending.get("reason"),
            }
        )
    return rows


def cleanup_delivered(
    target: Path, source: Path, members: list[dict[str, str]]
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """Sweep every registered workspace after publication with the one predicate."""

    branch, published = fresh_delivery(target)
    inventory = wt.worktrees(target)
    protected = frozenset(
        (target.resolve(), *(item.path for item in inventory if item.branch == branch))
    )
    admitted = {row["branch"]: row["original"] for row in members}
    parents = git_output(target, "show", "-s", "--format=%P", "HEAD").split()
    removed: list[dict[str, object]] = []
    retained: list[dict[str, str]] = []
    for item in inventory:
        if item.path in protected:
            continue
        if item.path == source.resolve():
            expected = parents[1] if len(parents) == 2 else None
            ending = removal(target, item, published, protected, expected_tip=expected)
        elif item.branch in admitted:
            ending = removal(target, item, published, protected, expected_tip=admitted[item.branch])
        else:
            ending = removal(target, item, published, protected, require_record=True)
        _settle(target, item, ending, removed, retained)
    return removed, retained
