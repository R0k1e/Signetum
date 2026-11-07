"""Stacked members: a member whose base is another open member's tip.

The workspace record names the parent branch. The parent tip a member holds is
its recorded base or the source of its latest parent synchronization, so the
member's own contribution never includes the parent's work.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import TypedDict

from signetum.git import git_output, run_git
from signetum.operations import AdmissionError
from signetum.synchronization import incorporated_parent_tip
from signetum.workspaces import (
    WorkspaceError,
    WorkspaceRecord,
    branch_checkouts,
    branch_name,
    read_record,
    state_root,
)

PARENT_SYNC = "maintenance workspace-sync --parent"


class ParentState(TypedDict):
    parent: str
    parent_tip: str
    parent_current: str | None
    sync_needed: bool
    admission_order: list[str]


def branch_tip(repository: Path, branch: str) -> str | None:
    completed = run_git(
        repository, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
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


def parent_state(repository: Path, record: WorkspaceRecord, tip: str) -> ParentState | None:
    """What a stacked member holds of its parent and whether the parent moved past it."""

    if record.parent is None:
        return None
    held = incorporated_parent_tip(repository, record.base, tip)
    current = branch_tip(repository, record.parent)
    return {
        "parent": record.parent,
        "parent_tip": held,
        "parent_current": current,
        "sync_needed": current is not None and not _is_ancestor(repository, current, tip),
        "admission_order": admission_order(repository, record.branch),
    }


def require_current_parent(
    repository: Path, record: WorkspaceRecord, tip: str, operation: str
) -> None:
    state = parent_state(repository, record, tip)
    if state is None or not state["sync_needed"]:
        return
    raise AdmissionError(
        f"{operation} refuses stacked member {record.branch}: its parent {record.parent} "
        f"advanced to {state['parent_current']} beyond the parent tip {state['parent_tip']} "
        "it holds",
        expected=f"run {PARENT_SYNC} in {repository}, then ready",
    )


def latest_admissions(batch: Path, base: str, tip: str) -> dict[str, str]:
    """Each member's latest admitted original in the batch's own history."""

    admitted: dict[str, str] = {}
    for merge in git_output(
        batch, "rev-list", "--reverse", "--first-parent", "--merges", f"{base}..{tip}"
    ).splitlines():
        body = git_output(batch, "show", "-s", "--format=%B", merge)
        member = re.findall(r"^Signetum-Member:\s*(\S+)$", body, re.MULTILINE)
        original = re.findall(r"^Signetum-Original:\s*(\S+)$", body, re.MULTILINE)
        if len(member) == 1 and len(original) == 1:
            admitted[member[0]] = original[0]
    return admitted


def require_parent_admitted(batch: Path, member: Path, record: WorkspaceRecord, tip: str) -> str:
    """Refuse a child whose exact parent tip is neither admitted nor already delivered.

    Earlier members of the same invocation have already merged, so the batch
    history at this moment answers for both an earlier admission and this one.
    """

    if record.parent is None:
        raise AdmissionError(f"member {record.branch} has no parent")
    held = incorporated_parent_tip(member, record.base, tip)
    batch_base = read_record(state_root(batch), branch_name(batch)).base
    if _is_ancestor(batch, held, batch_base):
        return held
    batch_tip = git_output(batch, "rev-parse", "HEAD")
    latest = latest_admissions(batch, batch_base, batch_tip).get(record.parent)
    if latest == held:
        return held
    order = admission_order(member, record.branch)
    if latest is None:
        reason = f"its parent {record.parent} is not admitted to this batch"
    else:
        reason = f"its parent {record.parent} is admitted at {latest}, not at parent tip {held}"
    paths = {name: path for name, path, _ in branch_checkouts(batch)}
    command = ["batch-admit", "--batch", str(batch)]
    for name in order:
        command.extend(("--member", str(paths.get(name, name))))
    raise AdmissionError(
        f"batch-admit refuses stacked member {record.branch}: {reason}; "
        f"admit the chain in order {' -> '.join(order)}",
        expected=shlex.join(command),
    )
