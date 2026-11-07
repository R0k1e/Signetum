"""Refuse two changes writing one decision clause identity concurrently.

Concurrent writes to one clause cannot both replay into the working set. The
projection would report that only after integration, so admission and batch
synchronization compare the committed contract identities first.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Mapping
from pathlib import Path, PurePosixPath

from signetum.change.paths import changes_root
from signetum.change_record import parse_change_record
from signetum.git import git_output, run_git
from signetum.manifest import RepositoryManifest
from signetum.operations import AdmissionError
from signetum.workspaces import WorkspaceError, read_change_owner, state_root

Claims = Mapping[str, frozenset[str]]


def clause_claims(
    repository: Path,
    manifest: RepositoryManifest,
    base: str,
    tip: str,
    *,
    own_paths: Collection[str] | None = None,
) -> dict[str, frozenset[str]]:
    """Clause identities each change record written since ``base`` claims at ``tip``.

    ``own_paths`` limits a member to its own contribution, so delivered records
    a verified synchronization brought in are not claimed again by the member.
    """

    root = PurePosixPath(changes_root(manifest))
    changed = git_output(
        repository, "diff", "--name-only", "-z", "--no-renames", base, tip, "--", str(root)
    )
    claims: dict[str, set[str]] = defaultdict(set)
    for line in sorted(filter(None, changed.split("\0"))):
        path = PurePosixPath(line)
        if path.name != "change.toml" or path.parent.parent != root:
            continue
        if own_paths is not None and line not in own_paths:
            continue
        shown = run_git(repository, "show", f"{tip}:{line}")
        if shown.returncode:
            continue
        try:
            record = parse_change_record(shown.stdout)
        except (ValueError, TypeError):
            # Qualification owns malformed records; this check reads only valid claims.
            continue
        for transaction in record.contract.decisions:
            for edit in transaction.clauses:
                for update in edit.updates:
                    claims[update.id].add(record.id)
    return {clause: frozenset(changes) for clause, changes in claims.items()}


def require_distinct_claims(
    incoming: Claims,
    existing: Claims,
    *,
    incoming_workspace: Callable[[str], str],
    existing_workspace: Callable[[str], str],
) -> None:
    collisions = [
        f"{clause} by change {left} in {incoming_workspace(left)} "
        f"and change {right} in {existing_workspace(right)}"
        for clause in sorted(incoming.keys() & existing.keys())
        for left in sorted(incoming[clause])
        for right in sorted(existing[clause])
        if left != right
    ]
    if collisions:
        raise AdmissionError(
            "decision clause identities are claimed concurrently: " + "; ".join(collisions),
            expected=(
                "give the clause a distinct identity in one change, commit it, "
                "run ready there and retry"
            ),
        )


def owning_workspace(repository: Path, fallback: str) -> Callable[[str], str]:
    """Name the member workspace that owns a change, else the given location."""

    def describe(change_id: str) -> str:
        try:
            owner = read_change_owner(state_root(repository), change_id)
        except WorkspaceError:
            owner = None
        return f"workspace {owner.member}" if owner is not None else fallback

    return describe
