"""One durable record of what a workspace is and which base it was cut from."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from re import fullmatch
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from signetum.git import git_output
from signetum.operations import AdmissionError, MergeConflict

WORKSPACE_DIRECTORY = "workspaces"


class WorkspaceError(ValueError):
    """A workspace record is missing, malformed, or already claimed."""


class WorkspaceRecord(BaseModel):
    """What a workspace is, written once when the workspace is created."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    branch: str = Field(min_length=1)
    base: str
    kind: Literal["member", "batch"]
    members: tuple[str, ...] = ()

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"unsupported workspace record schema: {value}")
        return value

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str) -> str:
        if fullmatch(r"[0-9a-f]{40,64}", value) is None:
            raise ValueError("workspace base must be an exact commit identity")
        return value

    @field_validator("members")
    @classmethod
    def validate_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("declared members must be unique")
        return value


class ChangeOwner(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    change_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    member: str = Field(min_length=1)


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
                current = ChangeOwner.model_validate_json(target.read_text(encoding="utf-8"))
            except (OSError, ValidationError) as error:
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
                stream.write(owner.model_dump_json() + "\n")
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
                stream.write(record.model_dump_json(indent=2) + "\n")
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
        return WorkspaceRecord.model_validate(document)
    except ValidationError as error:
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        message = str(first["msg"]).removeprefix("Value error, ")
        raise WorkspaceError(
            f"workspace record for {branch} is invalid: {f'{field}: ' if field else ''}{message}"
        ) from error


__all__ = [
    "WORKSPACE_DIRECTORY",
    "WorkspaceError",
    "WorkspaceRecord",
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
