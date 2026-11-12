"""Stacked members: a member whose base is another open member's tip.

The member's workspace record is the only source of the chain: it names the
parent branch, and its base is the parent tip it was opened on. The parent tip
a member holds is that base or the source of its latest parent synchronization.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from signetum.git import git_output, run_git
from signetum.operations import AdmissionError
from signetum.provenance import latest_admission_original
from signetum.synchronization import incorporated_parent_tip
from signetum.workspaces import (
    WorkspaceError,
    WorkspaceRecord,
    branch_checkouts,
    branch_name,
    read_record,
    state_root,
)


def branch_tip(repository: Path, branch: str) -> str | None:
    completed = run_git(
        repository, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    completed = run_git(repository, "merge-base", "--is-ancestor", ancestor, descendant)
    if completed.returncode not in (0, 1):
        raise AdmissionError(completed.stderr.strip() or "cannot establish parent ancestry")
    return completed.returncode == 0


def stacked_parent(repository: Path, base: str, delivery_branch: str) -> str | None:
    """Name the member branch a workspace-open base refers to, when it is one."""

    if base == delivery_branch or branch_tip(repository, base) is None:
        return None
    try:
        record = read_record(state_root(repository), base)
    except WorkspaceError:
        return None
    return base if record.kind == "member" else None


def admission_order(repository: Path, branch: str) -> list[str]:
    """The chain from its root member down to ``branch``, in admission order."""

    chain: list[str] = []
    current: str | None = branch
    while current is not None and current not in chain:
        chain.append(current)
        try:
            current = read_record(state_root(repository), current).parent
        except WorkspaceError:
            current = None
    return list(reversed(chain))


def parent_moved(repository: Path, record: WorkspaceRecord, tip: str) -> str | None:
    """The open parent's tip when it has moved past what this member holds."""

    if record.parent is None:
        return None
    current = branch_tip(repository, record.parent)
    if current is None or is_ancestor(repository, current, tip):
        return None
    return current


def require_current_parent(
    repository: Path, record: WorkspaceRecord, tip: str, operation: str
) -> None:
    current = parent_moved(repository, record, tip)
    if current is None:
        return
    held = incorporated_parent_tip(repository, record.base, tip)
    raise AdmissionError(
        f"{operation} refuses stacked member {record.branch}: its parent {record.parent} "
        f"advanced to {current} beyond the parent tip {held} it holds",
        expected=f"run maintenance workspace-sync in {repository}, then ready",
    )


def _latest_admission(batch: Path, base: str, tip: str, member: str) -> str | None:
    """A member's latest admitted original in the batch's own history."""

    return latest_admission_original(batch, base, tip, member)


def require_parent_admitted(batch: Path, member: Path, record: WorkspaceRecord, tip: str) -> None:
    """Refuse a child whose exact parent tip is neither admitted nor already in the base.

    Earlier members of the same invocation have already merged, so the batch
    history at this moment answers for both an earlier admission and this one.
    """

    if record.parent is None:
        return
    held = incorporated_parent_tip(member, record.base, tip)
    batch_base = read_record(state_root(batch), branch_name(batch)).base
    if is_ancestor(batch, held, batch_base):
        return
    batch_tip = git_output(batch, "rev-parse", "HEAD")
    latest = _latest_admission(batch, batch_base, batch_tip, record.parent)
    if latest == held:
        return
    order = admission_order(member, record.branch)
    reason = (
        f"its parent {record.parent} is not admitted to this batch"
        if latest is None
        else f"its parent {record.parent} is admitted at {latest}, not at parent tip {held}"
    )
    paths = {name: path for name, path, _ in branch_checkouts(batch)}
    command = ["batch-admit", "--batch", str(batch)]
    for name in order:
        command.extend(("--member", str(paths.get(name, name))))
    raise AdmissionError(
        f"batch-admit refuses stacked member {record.branch}: {reason}; "
        f"admit the chain in order {' -> '.join(order)}",
        expected=shlex.join(command),
    )
