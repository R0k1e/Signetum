# Generated from signetum.workspaces; edit the engine source and regenerate.
"""One durable record of what a workspace is and which base it was cut from."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from re import fullmatch
from typing import Literal, cast
from urllib.parse import quote

from .git import git_output
from .operations import AdmissionError, MergeConflict

WORKSPACE_DIRECTORY = "workspaces"


class WorkspaceError(ValueError):
    """A workspace record is missing, malformed, or already claimed."""


@dataclass(frozen=True)
class WorkspaceRecord:
    """What a workspace is, written once when the workspace is created."""

    schema_version: int
    branch: str
    base: str
    kind: Literal["member", "batch"]
    members: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise WorkspaceError(f"unsupported workspace record schema: {self.schema_version}")
        if not isinstance(self.branch, str) or not self.branch:
            raise WorkspaceError("workspace record branch is invalid")
        if (
            not isinstance(self.base, str)
            or fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.base) is None
        ):
            raise WorkspaceError("workspace base must be an exact commit identity")
        if self.kind not in ("member", "batch"):
            raise WorkspaceError("workspace record kind is invalid")
        if not isinstance(self.members, tuple) or any(
            not isinstance(member, str) or not member for member in self.members
        ):
            raise WorkspaceError("declared members must be non-empty strings")
        if len(self.members) != len(set(self.members)):
            raise WorkspaceError("declared members must be unique")


def parse_record(document: object) -> WorkspaceRecord:
    """Normalize JSON arrays, then apply the one record validator."""
    required = {"schema_version", "branch", "base", "kind"}
    if (
        not isinstance(document, dict)
        or not required.issubset(document)
        or set(document) - (required | {"members"})
    ):
        raise WorkspaceError("workspace record fields are invalid")
    members = document.get("members", ())
    if isinstance(members, list):
        members = tuple(members)
    return WorkspaceRecord(
        schema_version=cast(int, document["schema_version"]),
        branch=cast(str, document["branch"]),
        base=cast(str, document["base"]),
        kind=cast(Literal["member", "batch"], document["kind"]),
        members=cast(tuple[str, ...], members),
    )


@dataclass(frozen=True)
class ChangeOwner:
    change_id: str
    member: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise WorkspaceError("change owner schema is invalid")
        if (
            not isinstance(self.change_id, str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.change_id) is None
        ):
            raise WorkspaceError("change owner identity is invalid")
        if not isinstance(self.member, str) or not self.member:
            raise WorkspaceError("change owner member is invalid")


def _parse_owner(document: object) -> ChangeOwner:
    if not isinstance(document, dict) or set(document) != {"schema_version", "change_id", "member"}:
        raise WorkspaceError("change owner fields are invalid")
    return ChangeOwner(
        schema_version=cast(int, document["schema_version"]),
        change_id=cast(str, document["change_id"]),
        member=cast(str, document["member"]),
    )


def claim_change(root: Path, change_id: str, member: str) -> None:
    """Bind one change to its implementation branch, shared by linked worktrees."""

    owner = ChangeOwner(change_id=change_id, member=member)
    directory = root / "changes" / change_id
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "owner.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        target = directory / "owner.json"
        if target.exists():
            try:
                current = _parse_owner(json.loads(target.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError) as error:
                raise WorkspaceError(f"change owner is unreadable: {change_id}") from error
            if current != owner:
                raise WorkspaceError(
                    f"change {change_id} already belongs to member {current.member}; "
                    "use its existing workspace"
                )
            return
        descriptor, temporary = tempfile.mkstemp(prefix="owner-", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(asdict(owner), separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)


def record_path(root: Path, branch: str) -> Path:
    """Return the record location for one branch inside the state root."""

    return root / WORKSPACE_DIRECTORY / f"{quote(branch, safe='')}.json"


def write_record(root: Path, record: WorkspaceRecord) -> Path:
    """Write one workspace record, refusing to restate an existing base.

    A base is written once. Rewriting it would make the record a second place
    to claim a base rather than the single place that holds one.
    """

    path = record_path(root, record.branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / "records.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            existing = read_record(root, record.branch)
            if existing.base != record.base:
                raise WorkspaceError(
                    f"workspace {record.branch} is already recorded at base {existing.base}"
                )
            if existing != record:
                raise WorkspaceError("workspace already has a different recorded identity")
            return path
        descriptor, temporary = tempfile.mkstemp(prefix="record-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(asdict(record), indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return path


def read_record(root: Path, branch: str) -> WorkspaceRecord:
    """Read the record for one branch, failing closed when it is unusable."""

    path = record_path(root, branch)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        # A base is never guessed. A workspace created before this record
        # existed is adopted by writing the base a human knows it was cut
        # from, once, at the named path.
        raise WorkspaceError(
            f"workspace {branch} has no recorded base at {path}; "
            "a workspace created by workspace-open carries one, and one created "
            "earlier is adopted by writing "
            '{"schema_version": 1, "branch": ..., "base": ..., "kind": "member"} '
            "there"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise WorkspaceError(f"workspace record for {branch} is unreadable: {error}") from error
    try:
        record = parse_record(document)
        if record.branch != branch:
            raise WorkspaceError("workspace record branch does not match its path")
        return record
    except WorkspaceError as error:
        raise WorkspaceError(f"workspace record for {branch} is invalid: {error}") from error


__all__ = [
    "WORKSPACE_DIRECTORY",
    "WorkspaceError",
    "WorkspaceRecord",
    "parse_record",
    "read_record",
    "record_path",
    "write_record",
]


def state_root(repository: Path) -> Path:
    common = Path(git_output(repository, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repository / common
    root = common.resolve() / "signetum"
    root.mkdir(parents=True, exist_ok=True)
    return root


def primary_worktree(repository: Path) -> Path:
    """Git lists the primary worktree first, regardless of the invoking member."""
    inventory = git_output(repository, "worktree", "list", "--porcelain", "-z", strip=False)
    first = inventory.split("\0", 1)[0]
    if not first.startswith("worktree "):
        raise WorkspaceError("primary Git worktree is unavailable")
    root = Path(first.removeprefix("worktree ")).resolve()
    if not root.is_dir():
        raise WorkspaceError("primary Git worktree is unavailable")
    return root


def workspace_destination(repository: Path, branch: str) -> Path:
    """Resolve a collision-free contained location before invoking any tool."""
    git_output(repository, "check-ref-format", "--branch", branch)
    primary = primary_worktree(repository)
    managed = primary / ".worktrees"
    if managed.is_symlink() or managed.resolve() != managed:
        raise WorkspaceError("managed workspace root must not escape the primary repository")
    # ELF linkers treat percent signs in output paths as temporary-file patterns.
    # Git forbids literal tildes in refs, so this escape remains injective.
    target = managed / quote(branch, safe="").replace("%", "~")
    if target.is_symlink() or target.resolve().parent != managed:
        raise WorkspaceError("workspace destination must remain inside .worktrees")
    return target


def exclude_workspaces(repository: Path) -> None:
    """Bootstrap ignored managed state even before the primary receives new source."""
    common = state_root(repository).parent
    exclude = common / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        content = stream.read()
        if "/.worktrees/" not in content.splitlines():
            stream.write(
                ("\n" if content and not content.endswith("\n") else "") + "/.worktrees/\n"
            )


def retire_record(root: Path, branch: str) -> None:
    """Retire an absent checkout's active registration without rewriting its base."""
    path = record_path(root, branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / "records.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path.unlink(missing_ok=True)


def recorded_base(repository: Path, branch: str | None = None) -> str:
    """Return the base this workspace was cut from.

    The record is the only authority. A base is never re-derived from commit
    prose, and never accepted from a caller who could name a different one.
    """

    resolved = branch if branch is not None else branch_name(repository)
    try:
        return read_record(state_root(repository), resolved).base
    except WorkspaceError as error:
        raise AdmissionError(str(error)) from error


def require_clean(worktree: Path) -> None:
    status = git_output(worktree, "status", "--porcelain")
    if status:
        raise AdmissionError(f"worktree is not clean: {worktree}")


def branch_name(worktree: Path) -> str:
    branch = git_output(worktree, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        raise AdmissionError(f"member has no branch: {worktree}")
    return branch


def require_no_merge(repository: Path) -> None:
    merge_head = Path(git_output(repository, "rev-parse", "--git-path", "MERGE_HEAD"))
    if not merge_head.is_absolute():
        merge_head = repository / merge_head
    if merge_head.is_file():
        raise MergeConflict(
            "batch has an open merge",
            expected=f"resolve and stage paths, then batch-continue {repository}",
        )


@contextmanager
def exclusive_batch(batch: Path) -> Iterator[None]:
    """Hold the batch for one operator, naming the holder when refusing.

    Two admissions interleaving in one batch worktree leave the loser's merge
    state as whatever the winner happened to leave behind.
    """

    root = state_root(batch) / "locks"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{quote(branch_name(batch), safe='')}.lock"
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.seek(0)
            holder = handle.read().strip() or "another process"
            raise AdmissionError(f"batch is held by {holder}") from error
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid {os.getpid()} since {datetime.now(UTC).isoformat()}\n")
        handle.flush()
        yield
    finally:
        handle.close()


def read_change_owner(root: Path, change_id: str) -> ChangeOwner | None:
    """Read the same immutable claim used by the writer; absence grants no claim."""
    if not change_id or fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", change_id) is None:
        raise WorkspaceError("change owner identity is invalid")
    target = root / "changes" / change_id / "owner.json"
    if not target.exists():
        return None
    try:
        owner = _parse_owner(json.loads(target.read_text()))
    except (ValueError, OSError) as error:
        raise WorkspaceError(f"change owner is unreadable: {change_id}") from error
    if owner.change_id != change_id:
        raise WorkspaceError("change owner identity differs from its path")
    return owner
