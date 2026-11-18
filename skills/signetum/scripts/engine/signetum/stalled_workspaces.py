"""Derive member workspaces that look stalled, from local Git and workspace records only.

Nothing is fetched, stored or started; the report is advisory and never blocks.
"""

import time
from pathlib import Path

from signetum.git import git_output
from signetum.workspaces import (
    WorkspaceError,
    branch_checkouts,
    read_record,
    record_path,
    state_root,
)

DEFAULT_UNCOMMITTED_MINUTES = 30
DEFAULT_IDLE_MINUTES = 60


def stalled_workspaces(
    repository: Path,
    delivery_branch: str | None,
    *,
    uncommitted_after: float = DEFAULT_UNCOMMITTED_MINUTES,
    idle_after: float = DEFAULT_IDLE_MINUTES,
    now: float | None = None,
) -> list[dict[str, object]]:
    """Member workspaces holding stale uncommitted changes or never committing past their base.

    Activity is the later of the tip commit and the workspace opening, so a fresh
    workspace on an old base is not stalled. ``uncommitted_after`` and ``idle_after``
    are minutes.
    """

    moment = time.time() if now is None else now
    root = state_root(repository)
    rows: list[dict[str, object]] = []
    for branch, path, head in branch_checkouts(repository):
        if branch == delivery_branch or not path.is_dir():
            continue
        try:
            record = read_record(root, branch)
        except WorkspaceError:
            continue
        if record.kind != "member":
            continue
        opened = record_path(root, branch).stat().st_mtime
        committed = float(git_output(path, "log", "-1", "--format=%ct", head))
        quiet = (moment - max(opened, committed)) / 60
        reasons: list[str] = []
        if git_output(path, "status", "--porcelain") and quiet > uncommitted_after:
            reasons.append("uncommitted_changes")
        waiting = (moment - opened) / 60
        if head == record.base and waiting > idle_after:
            reasons.append("no_commits_beyond_base")
        if reasons:
            rows.append(
                {
                    "branch": branch,
                    "worktree": str(path),
                    "reasons": reasons,
                    "minutes_since_activity": int(quiet),
                    "minutes_since_opened": int(waiting),
                }
            )
    return rows
