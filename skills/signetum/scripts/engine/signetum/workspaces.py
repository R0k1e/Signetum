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

from signetum.git import GitError, git_output, repository_path, run_git
from signetum.operations import AdmissionError, MergeConflict

WORKSPACE_DIRECTORY = "workspaces"


class WorkspaceError(ValueError):
    """A workspace record is missing, malformed, or already claimed."""


@dataclass(frozen=True)
class BatchAuthorization:
    """Owner authorization captured once when the batch opens."""

    actor: str
    source: str
    recorded_at: str
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.actor, self.source, self.recorded_at)
        ):
            raise WorkspaceError("batch authorization requires actor, source and timestamp")
        try:
            moment = datetime.fromisoformat(self.recorded_at)
        except ValueError as error:
            raise WorkspaceError("batch authorization timestamp is invalid") from error
        if moment.tzinfo is None:
            raise WorkspaceError("batch authorization timestamp requires a timezone")
        if (
            not isinstance(self.members, tuple)
            or not self.members
            or any(not isinstance(member, str) or not member for member in self.members)
            or len(set(self.members)) != len(self.members)
        ):
            raise WorkspaceError("batch authorization members are invalid")


@dataclass(frozen=True)
class BatchEngine:
    """Immutable batch-opening identity; repository engines pin the location."""

    version: str
    implementation: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise WorkspaceError("batch engine version is invalid")
        if (
            not isinstance(self.implementation, str)
            or fullmatch(r"sha256:[0-9a-f]{64}", self.implementation) is None
        ):
            raise WorkspaceError("batch engine implementation is invalid")
        if self.source not in ("skill", "repository"):
            raise WorkspaceError("batch engine source is invalid")


@dataclass(frozen=True)
class WorkspaceRecord:
    """What a workspace is, written once when the workspace is created."""

    schema_version: int
    branch: str
    base: str
    kind: Literal["member", "batch"]
    members: tuple[str, ...] = ()
    # A stacked member names the member branch whose tip is its base.
    parent: str | None = None

    authorization: BatchAuthorization | None = None
    engine: BatchEngine | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version not in (1, 2):
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
        if self.authorization is not None and (
            not isinstance(self.authorization, BatchAuthorization)
            or self.kind != "batch"
            or self.schema_version != 2
            or self.authorization.members != self.members
        ):
            raise WorkspaceError("only schema-2 batches carry matching authorization")
        if self.engine is not None and (
            not isinstance(self.engine, BatchEngine)
            or self.kind != "batch"
            or self.schema_version != 2
        ):
            raise WorkspaceError("only schema-2 batches carry an engine pin")
        if self.parent is not None and (
            not isinstance(self.parent, str)
            or not self.parent
            or self.kind != "member"
            or self.parent == self.branch
        ):
            raise WorkspaceError("only a member names another member as its parent")


def record_document(record: WorkspaceRecord) -> dict[str, object]:
    """Serialize a record, omitting the parent of an ordinary workspace."""

    document = asdict(record)
    if record.parent is None:
        del document["parent"]
    if record.authorization is None:
        del document["authorization"]
    if record.engine is None:
        del document["engine"]
    return document


def parse_record(document: object) -> WorkspaceRecord:
    """Normalize JSON arrays, then apply the one record validator."""
    required = {"schema_version", "branch", "base", "kind"}
    if (
        not isinstance(document, dict)
        or not required.issubset(document)
        or set(document) - (required | {"members", "parent", "authorization", "engine"})
    ):
        raise WorkspaceError("workspace record fields are invalid")
    members = document.get("members", ())
    if isinstance(members, list):
        members = tuple(members)
    authorization = document.get("authorization")
    if authorization is not None:
        if not isinstance(authorization, dict) or set(authorization) != {
            "actor",
            "source",
            "recorded_at",
            "members",
        }:
            raise WorkspaceError("batch authorization fields are invalid")
        authorization = BatchAuthorization(
            actor=authorization["actor"],
            source=authorization["source"],
            recorded_at=authorization["recorded_at"],
            members=tuple(authorization["members"])
            if isinstance(authorization["members"], list)
            else authorization["members"],
        )
    engine = document.get("engine")
    if engine is not None:
        if not isinstance(engine, dict) or set(engine) != {"version", "implementation", "source"}:
            raise WorkspaceError("batch engine fields are invalid")
        engine = BatchEngine(**engine)
    return WorkspaceRecord(
        schema_version=cast(int, document["schema_version"]),
        branch=cast(str, document["branch"]),
        base=cast(str, document["base"]),
        kind=cast(Literal["member", "batch"], document["kind"]),
        members=cast(tuple[str, ...], members),
        parent=cast(str | None, document.get("parent")),
        authorization=authorization,
        engine=engine,
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
    to claim a base rather than the single place that holds one. Only batch
    synchronization advances a batch base, through ``advance_batch_base``.
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
                stream.write(json.dumps(record_document(record), indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return path


def advance_batch_base(root: Path, branch: str, previous: str, base: str) -> None:
    """Move a batch base to the delivery tip its committed synchronization merged.

    This is the one exception to a base being written once. The caller has
    proven that ``base`` descends from ``previous`` and that the batch history
    now contains it, so the record still agrees with committed provenance.
    """

    path = record_path(root, branch)
    with (path.parent / "records.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = read_record(root, branch)
        if existing.kind != "batch":
            raise WorkspaceError(f"only a batch base advances: {branch}")
        if existing.base == base:
            return
        if existing.base != previous:
            raise WorkspaceError(
                f"batch {branch} is recorded at base {existing.base}, not {previous}"
            )
        advanced = WorkspaceRecord(
            schema_version=existing.schema_version,
            branch=branch,
            base=base,
            kind="batch",
            members=existing.members,
            authorization=existing.authorization,
            engine=existing.engine,
        )
        descriptor, temporary = tempfile.mkstemp(prefix="record-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(asdict(advanced), indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


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
    common = repository_path(repository, "rev-parse", "--git-common-dir").resolve()
    root = common / "signetum"
    root.mkdir(parents=True, exist_ok=True)
    return root


def primary_worktree(repository: Path) -> Path:
    """Git lists the primary worktree first, regardless of the invoking member."""
    inventory = git_output(repository, "worktree", "list", "--porcelain", strip=False)
    first = inventory.split("\n\n", 1)[0]
    line = first.split("\n", 1)[0]
    if not line.startswith("worktree "):
        raise WorkspaceError("primary Git worktree is unavailable")
    root = Path(line.removeprefix("worktree ")).resolve()
    if not root.is_dir():
        raise WorkspaceError("primary Git worktree is unavailable")
    return root


def branch_checkouts(repository: Path) -> tuple[tuple[str, Path, str], ...]:
    """Read Git's own checkout listing without running Worktrunk.

    Read-only views use this offline listing; removal still goes through the
    Worktrunk inventory. A detached checkout is not a workspace.
    """
    inventory = git_output(repository, "worktree", "list", "--porcelain", strip=False)
    checkouts: list[tuple[str, Path, str]] = []
    for block in inventory.split("\n\n"):
        fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        branch = fields.get("branch", "")
        if "worktree" in fields and "HEAD" in fields and branch.startswith("refs/heads/"):
            path = Path(fields["worktree"]).resolve()
            checkouts.append((branch.removeprefix("refs/heads/"), path, fields["HEAD"]))
    return tuple(checkouts)


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
    exclude_pattern(repository, "/.worktrees/")


def exclude_pattern(repository: Path, pattern: str) -> None:
    """Add one pattern to the repository's shared info/exclude once."""
    common = state_root(repository).parent
    exclude = common / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        content = stream.read()
        if pattern not in content.splitlines():
            stream.write(("\n" if content and not content.endswith("\n") else "") + pattern + "\n")


RETIRED_DIRECTORY = "retired"


def retire_record(root: Path, branch: str, tip: str, ending: dict[str, object]) -> Path:
    """Keep the removed workspace's identity and proven outcome, then retire its registration.

    The retirement record is machine-local evidence beside the registrations. It
    keeps the tip, so an abandoned branch can be recreated while Git retains it.
    """
    path = record_path(root, branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    retired = root / RETIRED_DIRECTORY / quote(branch, safe="")
    retired.mkdir(parents=True, exist_ok=True)
    with (path.parent / "records.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            record: dict[str, object] | None = record_document(read_record(root, branch))
        except WorkspaceError:
            record = None
        moment = datetime.now(UTC)
        document = {
            "schema_version": 1,
            "branch": branch,
            "tip": tip,
            "record": record,
            "retired_at": moment.isoformat(),
            **ending,
        }
        descriptor, temporary = tempfile.mkstemp(
            prefix=f"{moment.strftime('%Y%m%dT%H%M%S%fZ')}-", suffix=".json", dir=retired
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        path.unlink(missing_ok=True)
    return Path(temporary)


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


def current_branch(repository: Path) -> str:
    """Return the short branch, or empty when HEAD is not a branch.

    Quiet symbolic-ref exits 1 when HEAD is not a branch. Other failures stay errors.
    """
    completed = run_git(repository, "symbolic-ref", "--quiet", "--short", "HEAD")
    if completed.returncode == 1:
        return ""
    if completed.returncode:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        raise GitError(diagnostic or "git symbolic-ref --quiet --short HEAD failed")
    return completed.stdout.strip()


def branch_name(worktree: Path) -> str:
    branch = git_output(worktree, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        raise AdmissionError(f"member has no branch: {worktree}")
    return branch


def require_no_merge(repository: Path) -> None:
    merge_head = repository_path(repository, "rev-parse", "--git-path", "MERGE_HEAD")
    if merge_head.is_file():
        raise MergeConflict(
            "batch has an open merge",
            expected=f"resolve and stage paths, then batch-continue --batch {repository}",
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
