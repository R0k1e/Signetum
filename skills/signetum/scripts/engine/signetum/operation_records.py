"""Versioned durable operations: one authority for sync, admission, and publication.

Pending intent is stored before Git effects. Completion binds the actual commit,
its parents, and its tree. Legacy history and already-pending old proofs stay
readable. A copied trailer never fills in a missing modern record.

The first use of this store records an open legacy merge that is already in
progress. It does not treat branch tips as trusted history. Explicit adoption
on this checkout is the only cutover for retained old history, including older
protocol merges and ordinary pre-protocol ancestry. Adoption makes that history
readable. It does not grant new provenance: only exact reviewed old-engine merge
text supplies historical sync, admission, publication, and baseline facts. A
copied trailer is not that proof. Import cannot install or expand a cutover; a
fresh checkout adopts the same commits itself. The cutover is the commits those
tips reach, not the branch name chosen from the local inventory. An equal
cutover imports without rewriting the destination record. A later merge without
a structured record stays modern. An older engine may have prepared or admitted
work before a self-hosted batch executes this source. Those commits remain
read-only. An engine handoff may also carry the declared preparation inputs
that engine needs. An earlier engine-only handoff stays readable and is not
rewritten; a later caller message and Ready source continue it in this store.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404 -- explicit argument vectors, never a shell
import sys
import tarfile
import tempfile
import threading
import tomllib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from signetum.git import GitError, git_output, repository_path, run_git
from signetum.operations import AdmissionError, MergeConflict, OperationFailed
from signetum.workspaces import (
    WorkspaceError,
    WorkspaceRecord,
    branch_checkouts,
    branch_name,
    read_record,
    state_root,
)

SCHEMA_VERSION = 1
# Qualification reads the operation index while completion already holds _lock.
# A second flock in the same process never returns, so the holding thread re-enters.
_lock_depth = threading.local()
# Binding one admission reads verified syncs from this index. The index must not
# validate that admission again, or the same check never returns.
_binding_ids: ContextVar[frozenset[str]] = ContextVar("signetum_binding_ids", default=frozenset())
KINDS = frozenset(
    {
        "member-sync",
        "batch-sync",
        "admission",
        "publication",
        "decision-mapping",
        "engine-handoff",
    }
)
SYNC_KINDS = frozenset({"delivery", "batch", "parent"})
_ENGINE_TREE = "skills/signetum/scripts/engine"
_LOCK_SOURCE_KEYS = frozenset({"editable", "path", "directory"})
MERGE_KINDS = frozenset({"member-sync", "batch-sync", "admission", "publication"})
_TRAILER = re.compile(r"^Signetum-", re.IGNORECASE)
_OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]*$")
_KNOWN_TRAILERS = frozenset(
    {
        "Signetum-Sync",
        "Signetum-Sync-Source",
        "Signetum-Base",
        "Signetum-Original",
        "Signetum-Member",
        "Signetum-Batch-Base",
        "Signetum-Batch-Tip",
        "Signetum-Batch-Sync",
        "Signetum-Previous-Batch-Base",
        "Signetum-Patch-ID",
        "Signetum-Ready-Evidence",
        "Signetum-Plan",
        "Signetum-Decision-Base",
        "Signetum-Decision-Rename",
    }
)
_LOCAL_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "kind",
        "status",
        "message",
        "branch",
        "before",
        "source",
        "base",
        "attested_base",
        "parents",
        "sync_kind",
        "previous_base",
        "member",
        "plans",
        "ready_evidence",
        "ready_evidence_sha256",
        "patch_id",
        "tree",
        "proof",
        "mappings",
        "continuation_messages",
    }
)
_EXPORT_FIELDS = _LOCAL_FIELDS - {"status", "continuation_messages"}


@dataclass(frozen=True)
class OperationIntent:
    """The identity and frozen message of one automatic commit."""

    kind: str
    branch: str
    before: str
    source: str
    base: str
    message: str
    attested_base: str
    parents: tuple[str, ...]
    sync_kind: str | None = None
    previous_base: str | None = None
    member: str | None = None
    plans: tuple[str, ...] = ()
    ready_evidence: str = ""
    ready_evidence_sha256: str = ""
    patch_id: str = ""
    tree: str | None = None
    mappings: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise AdmissionError(f"operation kind is invalid: {self.kind}")
        if not self.parents or self.parents[0] != self.before:
            raise AdmissionError("operation parents do not start at its before commit")

    def identity(self) -> str:
        payload = {
            "base": self.base,
            "before": self.before,
            "branch": self.branch,
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "source": self.source,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def _oid(value: object, name: str) -> str:
    if not isinstance(value, str) or _OID.fullmatch(value) is None:
        raise AdmissionError(f"operation {name} is not a commit id")
    return value


def _trailer_lines(message: str) -> tuple[str, ...]:
    return tuple(line for line in message.splitlines() if _TRAILER.match(line.lstrip()))


def _object_kind(repository: Path, oid: str) -> str:
    try:
        return git_output(repository, "cat-file", "-t", oid)
    except GitError as error:
        raise AdmissionError(f"operation object is unavailable: {oid}") from error


def _require_object(repository: Path, oid: str, kind: str, name: str) -> None:
    actual = _object_kind(repository, oid)
    if actual != kind:
        raise AdmissionError(f"operation {name} is not a {kind}")


def _reachable(repository: Path, commit: str) -> bool:
    """True when a local branch can already see ``commit``."""

    for oid in _branch_tips(repository).values():
        if oid == commit or _ancestor(repository, commit, oid):
            return True
    head = run_git(repository, "rev-parse", "--verify", "HEAD")
    if head.returncode == 0:
        current = head.stdout.strip()
        if current == commit or _ancestor(repository, commit, current):
            return True
    return False


def _branch_tips(repository: Path) -> dict[str, str]:
    output = git_output(
        repository, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", strip=False
    )
    tips = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        ref, _, oid = line.partition(" ")
        if ref and oid:
            tips[ref] = oid
    return tips


def _legacy_merge_message(message: str) -> bool:
    """True only for an old engine's exact merge text, not a copied trailer line."""

    if set(_trailer_lines(message)) != set(
        line for line in message.splitlines() if line.startswith("Signetum-")
    ):
        return False
    trailers = {
        line.split(":", 1)[0]: line.split(":", 1)[1].strip()
        for line in _trailer_lines(message)
        if ":" in line
    }
    if any(key not in _KNOWN_TRAILERS for key in trailers):
        return False
    subject, _, _rest = message.partition("\n\n")
    if trailers.keys() >= {"Signetum-Sync", "Signetum-Sync-Source"} and set(trailers) <= {
        "Signetum-Sync",
        "Signetum-Sync-Source",
    }:
        return (
            subject.startswith("Merge ")
            and " into " in subject
            and bool(_OID.fullmatch(trailers["Signetum-Sync"]))
        )
    if trailers.keys() >= {
        "Signetum-Batch-Sync",
        "Signetum-Batch-Base",
        "Signetum-Previous-Batch-Base",
    }:
        return subject.startswith("Merge delivered history into ")
    publication = {"Signetum-Batch-Base", "Signetum-Batch-Tip"} <= set(trailers)
    if publication and "Signetum-Member" not in trailers:
        return subject.startswith("Merge ") and " into " in subject
    required = {
        "Signetum-Base",
        "Signetum-Original",
        "Signetum-Member",
        "Signetum-Batch-Base",
        "Signetum-Patch-ID",
        "Signetum-Ready-Evidence",
    }
    return (
        required <= set(trailers)
        and subject.startswith("Merge ")
        and subject.endswith(" into integration batch")
    )


def legacy_proof_message(message: str) -> bool:
    """Exact old-engine merge text. Adopted history can be read without this proof."""

    return _legacy_merge_message(message)


def legacy_publication_message(task: str, target_branch: str, base: str, tip: str) -> str:
    """The exact publication text the 0.9.1 engine stored."""

    return (
        f"Merge {task} into {target_branch}\n\n"
        f"Signetum-Batch-Base: {base}\n"
        f"Signetum-Batch-Tip: {tip}\n"
    )


def freeze_message(message: str) -> str:
    """Accept caller text and keep the exact bytes Git will store."""

    if "\0" in message:
        raise AdmissionError("commit message contains NUL")
    if not message.strip():
        raise AdmissionError("commit message is empty")
    if not message.endswith("\n"):
        message += "\n"
    return message


def read_message_file(path: Path) -> str:
    """Read one message file before any Git effect. The returned text is frozen."""

    if not path.is_file():
        raise AdmissionError(f"message file is missing: {path.name}")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise AdmissionError(f"message file is unreadable: {path.name}") from error
    if b"\0" in data:
        raise AdmissionError("commit message contains NUL")
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise AdmissionError("commit message is not UTF-8") from error
    return freeze_message(text)


def read_message_files(paths: Sequence[Path]) -> tuple[str, ...]:
    if not paths:
        raise AdmissionError("a message file is required")
    return tuple(read_message_file(path) for path in paths)


def commit_message(repository: Path, commit: str) -> str:
    raw = git_output(repository, "cat-file", "commit", commit, strip=False)
    head, separator, body = raw.partition("\n\n")
    if separator and head.startswith("tree "):
        return body
    raise AdmissionError("commit message is unreadable")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(document: Mapping[str, object]) -> str:
    return json.dumps(document, sort_keys=True, indent=2) + "\n"


def _records_root(root: Path) -> Path:
    directory = root / "operations" / "records"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _qualifications(root: Path) -> Path:
    directory = root / "operations" / "qualifications"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def _lock(repository: Path) -> Iterator[Path]:
    """Serialize every writer at the shared Git common directory.

    The holding thread may re-enter. Completion validates a record while it
    holds this lock, and that validation reads the same index.
    """

    root = state_root(repository)
    operations = root / "operations"
    operations.mkdir(parents=True, exist_ok=True)
    lock_path = operations / ".lock"
    key = str(lock_path)
    held = getattr(_lock_depth, "held", None)
    if held is None:
        held = {}
        _lock_depth.held = held
    if held.get(key, 0):
        held[key] += 1
        try:
            yield root
        finally:
            held[key] -= 1
        return
    handle = lock_path.open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        held[key] = 1
        try:
            yield root
        finally:
            held[key] -= 1
    finally:
        handle.close()


def _write_atomic(destination: Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".operation-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def _record_path(root: Path, identity: str) -> Path:
    if re.fullmatch(r"[0-9a-f]{64}", identity) is None:
        raise AdmissionError("operation identity is invalid")
    return _records_root(root) / f"{identity}.json"


def _known_trailer(line: str) -> bool:
    if _TRAILER.match(line) is None or ":" not in line:
        return False
    key, value = line.split(":", 1)
    return key in _KNOWN_TRAILERS and bool(value.strip()) and "\n" not in value


def _open_pending_merges(repository: Path) -> list[dict[str, object]]:
    """Snapshot only a merge this worktree already has open, with its real trailers."""

    found: list[dict[str, object]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for _, checkout, _ in branch_checkouts(repository):
        path = repository_path(checkout, "rev-parse", "--git-path", "signetum-pending-merge.json")
        document = _read_json(path)
        if document is None:
            continue
        trailers = document.get("trailers")
        before = document.get("before")
        source = document.get("source")
        if (
            not isinstance(before, str)
            or _OID.fullmatch(before) is None
            or not isinstance(source, str)
            or _OID.fullmatch(source) is None
            or not isinstance(trailers, list)
            or not trailers
            or not all(isinstance(item, str) and _known_trailer(item) for item in trailers)
        ):
            continue
        head = run_git(checkout, "rev-parse", "--verify", "HEAD")
        merge_head = run_git(checkout, "rev-parse", "--verify", "MERGE_HEAD")
        if head.returncode != 0 or merge_head.returncode != 0:
            continue
        if head.stdout.strip() != before or merge_head.stdout.strip() != source:
            continue
        message_path = repository_path(checkout, "rev-parse", "--git-path", "MERGE_MSG")
        try:
            message = message_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        actual = tuple(sorted(_trailer_lines(message)))
        if actual != tuple(sorted(trailers)):
            continue
        key = (before, source, tuple(trailers))
        if key in seen:
            continue
        seen.add(key)
        trailer_lines: list[object] = []
        for item in trailers:
            if isinstance(item, str):
                trailer_lines.append(item)
        entry: dict[str, object] = {}
        entry["before"] = before
        entry["source"] = source
        entry["trailers"] = trailer_lines
        found.append(entry)
    return found


def _sync_digests(root: Path) -> list[str]:
    directory = root / "synchronization"
    if not directory.is_dir():
        return []
    digests = []
    for path in sorted(directory.glob("*.json")):
        try:
            digests.append(_digest(path.read_bytes()))
        except OSError:
            continue
    return digests


def _ensure_horizon(repository: Path, root: Path) -> dict[str, object]:
    """Record open legacy merges once. Branch tips are not inferred as trust."""

    path = root / "operations" / "legacy-horizon.json"
    document = _read_json(path)
    if document is not None and document.get("schema_version") == SCHEMA_VERSION:
        if "adopted" not in document:
            document = {**document, "adopted": False}
        return document
    if path.exists():
        raise AdmissionError(
            "legacy operation horizon is unreadable",
            expected="restore the recorded horizon or retry from a repository that has one",
        )
    horizon = {
        "schema_version": SCHEMA_VERSION,
        "adopted": False,
        "tips": {},
        "pending_merges": _open_pending_merges(repository),
        "sync_record_sha256": _sync_digests(root),
    }
    _write_atomic(path, _canonical(horizon))
    return horizon


def _ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    completed = run_git(repository, "merge-base", "--is-ancestor", ancestor, descendant)
    if completed.returncode not in (0, 1):
        raise AdmissionError(completed.stderr.strip() or "cannot compare legacy history")
    return completed.returncode == 0


def _proof_commits(root: Path) -> list[str]:
    records = root / "operations" / "records"
    if not records.is_dir():
        return []
    found = []
    for path in records.glob("*.json"):
        document = _read_json(path)
        if not isinstance(document, dict) or document.get("status") != "completed":
            continue
        proof = document.get("proof")
        if isinstance(proof, dict) and isinstance(proof.get("commit"), str):
            found.append(str(proof["commit"]))
    return found


def _in_horizon(
    repository: Path, horizon: Mapping[str, object], commit: str, modern: Sequence[str] = ()
) -> bool:
    if horizon.get("adopted") is not True:
        return False
    tips = horizon.get("tips")
    if not isinstance(tips, dict) or not tips:
        return False
    if any(item == commit or _ancestor(repository, item, commit) for item in modern):
        return False
    return any(
        isinstance(oid, str) and (oid == commit or _ancestor(repository, commit, oid))
        for oid in tips.values()
    )


def legacy_commit(repository: Path, commit: str) -> bool:
    """True when an explicit adoption still covers ``commit`` and no later operation does."""

    with _lock(repository) as root:
        horizon = _ensure_horizon(repository, root)
        modern = _proof_commits(root)
    return _in_horizon(repository, horizon, commit, modern)


def legacy_pending_trailers(repository: Path, before: str, source: str) -> tuple[str, ...] | None:
    """Trailers of an old merge that was already pending when this engine started."""

    with _lock(repository) as root:
        horizon = _ensure_horizon(repository, root)
    pending = horizon.get("pending_merges")
    if not isinstance(pending, list):
        return None
    for item in pending:
        if (
            isinstance(item, dict)
            and item.get("before") == before
            and item.get("source") == source
            and isinstance(item.get("trailers"), list)
        ):
            trailers = item["trailers"]
            if trailers and all(isinstance(line, str) for line in trailers):
                return tuple(trailers)
    return None


def snapshotted_sync_record(repository: Path, path: Path) -> bool:
    """True when this legacy sync file existed before the horizon."""

    try:
        digest = _digest(path.read_bytes())
    except OSError:
        return False
    with _lock(repository) as root:
        horizon = _ensure_horizon(repository, root)
    recorded = horizon.get("sync_record_sha256")
    return isinstance(recorded, list) and digest in recorded


def legacy_pending_commit(repository: Path, commit: str) -> bool:
    """A commit that finishes one snapshotted old pending merge, and nothing else."""

    try:
        parents = git_output(repository, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        message = commit_message(repository, commit)
    except (GitError, AdmissionError):
        return False
    if len(parents) != 2:
        return False
    trailers = legacy_pending_trailers(repository, parents[0], parents[1])
    if trailers is None:
        return False
    actual = tuple(sorted(line for line in message.splitlines() if _TRAILER.match(line.lstrip())))
    return actual == tuple(sorted(trailers))


def _numbering_mappings(
    repository: Path, before: str, commit: str, directory: str
) -> tuple[tuple[str, str], ...]:
    """Numbering renames actually stored between ``before`` and ``commit``."""

    diff = git_output(
        repository,
        "diff",
        "--name-status",
        "--find-renames",
        before,
        commit,
        "--",
        directory,
        strip=False,
    )
    found: list[tuple[str, str]] = []
    for line in diff.splitlines():
        if not line.startswith("R"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        old, new = parts[1], parts[2]
        numbered = re.fullmatch(r"ADP-\d{4}-(.+)\.md", Path(new).name)
        if (
            numbered is None
            or Path(old).parent.as_posix() != directory
            or Path(new).parent.as_posix() != directory
            or old == new
            or Path(old).name != f"ADP-proposal-{numbered.group(1)}.md"
        ):
            continue
        found.append((old, new))
    return tuple(found)


def _json_list(value: object, diagnostic: str) -> list[object]:
    if not isinstance(value, list):
        raise AdmissionError(diagnostic)
    return list(value)


def _string_keyed_dict(value: object, diagnostic: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AdmissionError(diagnostic)
    copied: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise AdmissionError(diagnostic)
        copied[key] = item
    return copied


def _mapping_pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise AdmissionError("operation mappings are invalid")
    pairs = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(part, str) and part for part in item)
        ):
            raise AdmissionError("operation mappings are invalid")
        pairs.append((item[0], item[1]))
    return tuple(pairs)


def validate_operation(
    repository: Path,
    document: Mapping[str, object],
    *,
    portable: bool = False,
    qualifications: Mapping[str, bytes] | None = None,
) -> dict[str, object]:
    """One contract for a local record or a portable proof.

    A recomputed id is not enough. Kind, parents, bases, tree, qualification
    and mappings have to agree with each other and with the Git objects.
    """

    if not isinstance(document, Mapping):
        raise AdmissionError("operation record is invalid")
    allowed = _EXPORT_FIELDS if portable else _LOCAL_FIELDS
    unknown = set(document) - allowed
    if unknown:
        raise AdmissionError(f"operation record has unknown fields: {', '.join(sorted(unknown))}")
    schema = document.get("schema_version")
    if schema != SCHEMA_VERSION or type(schema) is not int:
        raise AdmissionError("operation record schema is unsupported")
    kind = document.get("kind")
    if kind not in KINDS:
        raise AdmissionError(f"operation kind is invalid: {kind}")
    identity = document.get("id")
    if not isinstance(identity, str) or _SHA256.fullmatch(identity) is None:
        raise AdmissionError("operation identity is invalid")
    message = document.get("message")
    if not isinstance(message, str) or message != freeze_message(message):
        raise AdmissionError("operation message is invalid")
    if _trailer_lines(message):
        raise AdmissionError("operation message cannot carry Signetum trailers")
    branch = document.get("branch")
    if not isinstance(branch, str) or not branch.strip() or branch != branch.strip():
        raise AdmissionError("operation branch is invalid")
    if ".." in branch or branch.startswith(("/", "~")):
        raise AdmissionError("operation branch is invalid")
    before = _oid(document.get("before"), "before")
    source = _oid(document.get("source"), "source")
    base = _oid(document.get("base"), "base")
    attested = _oid(document.get("attested_base"), "attested base")
    parents = document.get("parents")
    if (
        not isinstance(parents, list)
        or not parents
        or not all(isinstance(item, str) and _OID.fullmatch(item) for item in parents)
    ):
        raise AdmissionError("operation parents are invalid")
    if parents[0] != before:
        raise AdmissionError("operation parents do not start at its before commit")
    plans = document.get("plans", [])
    if not isinstance(plans, list) or not all(isinstance(item, str) for item in plans):
        raise AdmissionError("operation plans are invalid")
    sync_kind = document.get("sync_kind")
    previous = document.get("previous_base")
    member = document.get("member")
    tree = document.get("tree")
    evidence = document.get("ready_evidence", "")
    digest = document.get("ready_evidence_sha256", "")
    patch = document.get("patch_id", "")
    if sync_kind is not None and (not isinstance(sync_kind, str) or sync_kind not in SYNC_KINDS):
        raise AdmissionError("operation sync kind is invalid")
    if previous is not None and (not isinstance(previous, str) or _OID.fullmatch(previous) is None):
        raise AdmissionError("operation previous base is invalid")
    if member is not None and (not isinstance(member, str) or not member.strip()):
        raise AdmissionError("operation member is invalid")
    if tree is not None and (not isinstance(tree, str) or _OID.fullmatch(tree) is None):
        raise AdmissionError("operation tree is invalid")
    if not isinstance(evidence, str) or not isinstance(patch, str):
        raise AdmissionError("operation evidence is invalid")
    if digest in ("", None):
        digest = ""
    if not isinstance(digest, str) or (digest and _SHA256.fullmatch(digest) is None):
        raise AdmissionError("operation qualification identity is invalid")
    if evidence and not digest:
        raise AdmissionError("operation qualification bytes are missing")
    if "mappings" not in document:
        raise AdmissionError("operation mappings are invalid")
    mappings = _mapping_pairs(document["mappings"])
    continuation = document.get("continuation_messages")
    if continuation is not None:
        if not isinstance(continuation, list) or not all(
            isinstance(item, str) and item == freeze_message(item) for item in continuation
        ):
            raise AdmissionError("stored continuation messages are invalid")
    status = "completed" if portable else document.get("status")
    if status not in {"pending", "completed"}:
        raise AdmissionError("operation status is invalid")
    proof = document.get("proof")
    if status == "pending":
        if proof is not None:
            raise AdmissionError("pending operation cannot carry proof")
    else:
        if not isinstance(proof, dict) or set(proof) != {"commit", "parents", "tree"}:
            raise AdmissionError("operation proof shape is invalid")
        proof_commit = _oid(proof.get("commit"), "proof commit")
        proof_parents = proof.get("parents")
        proof_tree = _oid(proof.get("tree"), "proof tree")
        if proof_parents != parents:
            raise AdmissionError("operation parents do not match its proof")
        if isinstance(tree, str) and tree != proof_tree:
            raise AdmissionError("operation tree does not match its proof")
        _require_object(repository, proof_commit, "commit", "proof commit")
        actual = git_proof(repository, proof_commit)
        if (
            actual["parents"] != parents
            or actual["tree"] != proof_tree
            or actual["message"] != message
        ):
            raise AdmissionError("operation proof does not match the Git object")
    for oid, name in (
        (before, "before"),
        (source, "source"),
        (base, "base"),
        (attested, "attested base"),
    ):
        _require_object(repository, oid, "commit", name)
    if isinstance(tree, str):
        _require_object(repository, tree, "tree", "tree")
    if kind in MERGE_KINDS:
        if parents != [before, source] or source == before:
            raise AdmissionError("operation source is not its second parent")
        if not _ancestor(repository, base, before) or not _ancestor(repository, base, source):
            raise AdmissionError("operation base is not an ancestor of the merge")
    if kind == "member-sync":
        if sync_kind is None or previous is not None or member is not None or mappings:
            raise AdmissionError("member synchronization record is invalid")
        if attested != base:
            raise AdmissionError("member synchronization attests a different base")
    elif kind == "batch-sync":
        if (
            sync_kind is not None
            or member is not None
            or mappings
            or previous != base
            or attested != source
        ):
            raise AdmissionError("batch synchronization record is invalid")
        if not _ancestor(repository, base, source):
            raise AdmissionError("batch synchronization does not descend from the previous base")
    elif kind == "admission":
        if (
            sync_kind is not None
            or previous is not None
            or not isinstance(member, str)
            or mappings
            or attested != base
            or not evidence
            or not digest
            or not patch
        ):
            raise AdmissionError("admission record is invalid")
    elif kind == "publication":
        if (
            sync_kind is not None
            or previous is not None
            or member is not None
            or mappings
            or attested != base
            or base != before
            or not isinstance(tree, str)
        ):
            raise AdmissionError("publication record is invalid")
        source_tree = git_output(repository, "rev-parse", f"{source}^{{tree}}")
        if tree != source_tree:
            raise AdmissionError("publication tree is not the published source tree")
    elif kind == "decision-mapping":
        if (
            sync_kind is not None
            or previous is not None
            or member is not None
            or parents != [before]
            or source == before
            or attested != base
            or not isinstance(tree, str)
            or not mappings
        ):
            raise AdmissionError("decision mapping record is invalid")
        if not _ancestor(repository, base, before):
            raise AdmissionError("decision mapping is not bound to the approved base")
        recorded = _numbering_mappings(repository, before, source, str(Path(mappings[0][0]).parent))
        if recorded != mappings:
            raise AdmissionError("decision mapping does not match the committed rename")
        if status == "completed" and isinstance(proof, dict) and proof.get("commit") != source:
            raise AdmissionError("decision mapping is not bound to its commit")
    elif kind == "engine-handoff":
        if (
            sync_kind is not None
            or previous is not None
            or member is not None
            or mappings
            or parents != [before]
            or source == before
            or attested != base
            or not isinstance(tree, str)
        ):
            raise AdmissionError("engine handoff record is invalid")
        if not _ancestor(repository, base, before):
            raise AdmissionError("engine handoff base is not an ancestor of the batch")
        if status == "completed" and isinstance(proof, dict):
            handoff = str(proof.get("commit"))
            _require_same_engine_tree(repository, source, handoff)
            changed = git_output(
                repository, "diff", "--name-only", before, handoff, strip=False
            ).splitlines()
            outside_engine = [
                path for path in changed if path and not path.startswith(f"{_ENGINE_TREE}/")
            ]
            # An engine-only effect stays valid without consulting later bindings.
            # Only paths this commit changes must be declared preparation inputs.
            if outside_engine:
                allowed = set(_preparation_bindings(repository, source))
                if any(path not in allowed for path in outside_engine):
                    raise AdmissionError(
                        "engine handoff changes more than the repository engine "
                        "and its declared preparation inputs"
                    )
                for path in outside_engine:
                    if _path_blob(repository, source, path) != _path_blob(
                        repository, handoff, path
                    ):
                        raise AdmissionError(
                            "engine handoff does not preserve the source preparation input"
                        )
    expected = intent_from_document({**document, "status": status, "proof": proof}).identity()
    if expected != identity:
        raise AdmissionError("operation identity does not match its fields")
    if digest:
        supplied = None if qualifications is None else qualifications.get(digest)
        if supplied is None:
            stored = qualification_bytes(repository, digest)
            if stored is not None:
                supplied = stored
        if supplied is not None and _digest(supplied) != digest:
            raise AdmissionError("operation qualification bytes are missing")
        if kind == "admission" and supplied is not None:
            _bind_admission_qualification(repository, document, supplied)
        elif status == "completed" and supplied is None:
            require_qualification(repository, digest)
    return dict(document)


def _bind_admission_qualification(
    repository: Path, document: Mapping[str, object], content: bytes
) -> None:
    """Guard one admission while the source owner binds its qualification.

    Digest equality only proves the bytes are intact. Source admission binds
    the receipt, plans, and patch for a local record and an import. Reading
    those rules consults the operation index and returns the stored records.
    Validating this admission again would never return.
    """

    identity = document.get("id")
    active = _binding_ids.get()
    if isinstance(identity, str) and identity in active:
        return
    bound = active | {identity} if isinstance(identity, str) else active
    token = _binding_ids.set(bound)
    try:
        # scope reaches this module through decision_identity. The source owner
        # already imports that chain; load it only while this check runs.
        from signetum.source_admission import bind_admission_qualification  # noqa: PLC0415

        bind_admission_qualification(repository, document, content)
    finally:
        _binding_ids.reset(token)


def _require_same_engine_tree(repository: Path, source: str, commit: str) -> None:
    try:
        source_tree = git_output(repository, "rev-parse", f"{source}:{_ENGINE_TREE}")
        commit_tree = git_output(repository, "rev-parse", f"{commit}:{_ENGINE_TREE}")
    except GitError as error:
        raise AdmissionError("engine handoff source has no repository engine") from error
    if source_tree != commit_tree:
        raise AdmissionError("engine handoff does not preserve the source engine")


def _horizon_merges_are_legacy(repository: Path, tip: str, modern: Sequence[str]) -> None:
    """Retained history may be older than the reviewed merge text.

    Exact proof still grants operation facts. The cutover itself only refuses a
    structured operation, which would make modern missing evidence look legacy.
    """

    if any(item == tip or _ancestor(repository, item, tip) for item in modern):
        raise AdmissionError("legacy adoption cannot include a structured operation")


def _validate_horizon_git(
    repository: Path, horizon: Mapping[str, object], *, modern: Sequence[str]
) -> None:
    tips = horizon.get("tips")
    pending = horizon.get("pending_merges")
    digests = horizon.get("sync_record_sha256")
    if (
        horizon.get("schema_version") != SCHEMA_VERSION
        or type(horizon.get("schema_version")) is not int
        or not isinstance(tips, dict)
        or not isinstance(pending, list)
        or not isinstance(digests, list)
        or horizon.get("adopted") not in {True, False}
    ):
        raise AdmissionError("legacy operation horizon is invalid")
    if any(not isinstance(item, str) or _SHA256.fullmatch(item) is None for item in digests):
        raise AdmissionError("legacy operation horizon is invalid")
    for ref, oid in tips.items():
        if not isinstance(ref, str) or _REF.fullmatch(ref) is None:
            raise AdmissionError("legacy horizon tip ref is invalid")
        commit = _oid(oid, "horizon tip")
        _require_object(repository, commit, "commit", "horizon tip")
        if not _reachable(repository, commit):
            raise AdmissionError("legacy horizon tip is not in this repository")
        if horizon.get("adopted") is True:
            _horizon_merges_are_legacy(repository, commit, modern)
    for item in pending:
        if not isinstance(item, dict) or set(item) - {"continuation_messages"} != {
            "before",
            "source",
            "trailers",
        }:
            raise AdmissionError("legacy horizon pending merge is invalid")
        before = _oid(item.get("before"), "pending before")
        source = _oid(item.get("source"), "pending source")
        trailers = item.get("trailers")
        if (
            not isinstance(trailers, list)
            or not trailers
            or not all(isinstance(line, str) and _known_trailer(line) for line in trailers)
        ):
            raise AdmissionError("legacy horizon pending merge is invalid")
        _require_object(repository, before, "commit", "pending before")
        _require_object(repository, source, "commit", "pending source")
        continuation = item.get("continuation_messages")
        if continuation is not None and (
            not isinstance(continuation, list)
            or not all(isinstance(line, str) and line.endswith("\n") for line in continuation)
        ):
            raise AdmissionError("legacy horizon continuation is invalid")
    _refuse_machine_paths(dict(horizon), "legacy_horizon")


def adopt_legacy_history(repository: Path, commits: Sequence[str]) -> dict[str, object]:
    """Adopt explicit pre-modern tips. This does not move the cutover forward."""

    if not commits:
        raise AdmissionError("legacy adoption requires a commit")
    selected: list[tuple[str, str]] = []
    for commit in commits:
        try:
            oid = git_output(repository, "rev-parse", f"{commit}^{{commit}}")
        except GitError as error:
            raise AdmissionError(f"legacy adoption commit is unavailable: {commit}") from error
        if not _reachable(repository, oid):
            raise AdmissionError("legacy adoption commit is not in this repository")
        containing = [
            ref
            for ref, tip in _branch_tips(repository).items()
            if tip == oid or _ancestor(repository, oid, tip)
        ]
        if not containing:
            raise AdmissionError("legacy adoption commit is not on a local branch")
        selected.append((containing[0], oid))
    with _lock(repository) as root:
        horizon = _ensure_horizon(repository, root)
        modern = _proof_commits(root)
        tips = _string_keyed_dict(horizon.get("tips") or {}, "legacy operation horizon is invalid")
        for ref, oid in selected:
            _horizon_merges_are_legacy(repository, oid, modern)
            previous = tips.get(ref)
            if isinstance(previous, str) and previous != oid:
                if _ancestor(repository, previous, oid):
                    raise AdmissionError("legacy adoption cannot expand the recorded cutover")
                if not _ancestor(repository, oid, previous):
                    raise AdmissionError("legacy adoption conflicts with the recorded cutover")
            tips[ref] = oid if not isinstance(previous, str) else previous
            shrinks = (
                isinstance(previous, str)
                and oid != previous
                and _ancestor(repository, oid, previous)
            )
            if shrinks:
                tips[ref] = oid
        adopted = {
            "schema_version": SCHEMA_VERSION,
            "adopted": True,
            "tips": tips,
            "pending_merges": horizon.get("pending_merges"),
            "sync_record_sha256": horizon.get("sync_record_sha256"),
        }
        _validate_horizon_git(repository, adopted, modern=modern)
        path = root / "operations" / "legacy-horizon.json"
        _write_atomic(path, _canonical(adopted))
    return adopted


def store_legacy_continuation(
    repository: Path, before: str, source: str, messages: Sequence[str]
) -> None:
    """Persist caller text for the members an old pending admission still owes."""

    frozen = [freeze_message(message) for message in messages]
    with _lock(repository) as root:
        horizon = _ensure_horizon(repository, root)
        pending = horizon.get("pending_merges")
        if not isinstance(pending, list):
            raise AdmissionError("legacy operation horizon is invalid")
        updated = []
        found = False
        for item in pending:
            if not isinstance(item, dict):
                raise AdmissionError("legacy operation horizon is invalid")
            if item.get("before") == before and item.get("source") == source:
                existing = item.get("continuation_messages")
                if existing is not None and existing != frozen:
                    raise AdmissionError(
                        "recorded operation conflicts with this request",
                        expected="retry the same continuation messages",
                    )
                updated.append({**item, "continuation_messages": frozen})
                found = True
            else:
                updated.append(dict(item))
        if not found:
            raise AdmissionError("batch has no recorded merge to continue")
        horizon = {**horizon, "pending_merges": updated}
        _write_atomic(root / "operations" / "legacy-horizon.json", _canonical(horizon))


def legacy_continuation_messages(
    repository: Path, before: str, source: str
) -> tuple[str, ...] | None:
    with _lock(repository) as root:
        horizon = _ensure_horizon(repository, root)
    pending = horizon.get("pending_merges")
    if not isinstance(pending, list):
        return None
    for item in pending:
        if isinstance(item, dict) and item.get("before") == before and item.get("source") == source:
            messages = item.get("continuation_messages")
            if messages is None:
                return None
            if not isinstance(messages, list) or not all(
                isinstance(line, str) for line in messages
            ):
                raise AdmissionError("stored continuation messages are invalid")
            return tuple(messages)
    return None


def _load_document(path: Path) -> dict[str, object]:
    document = _read_json(path)
    if document is None or document.get("schema_version") != SCHEMA_VERSION:
        raise AdmissionError(f"operation record is unreadable: {path.name}")
    return document


def _documents(root: Path) -> list[dict[str, object]]:
    records = _records_root(root)
    loaded = []
    for path in sorted(records.glob("*.json")):
        loaded.append(_load_document(path))
    return loaded


@dataclass(frozen=True)
class OperationIndex:
    by_id: dict[str, dict[str, object]]
    by_commit: dict[str, dict[str, object]]

    def for_commit(self, commit: str) -> dict[str, object] | None:
        return self.by_commit.get(commit)


def _operation_index(documents: Iterable[Mapping[str, object]]) -> OperationIndex:
    stored = [dict(document) for document in documents]
    _reject_duplicate_proofs(stored)
    by_id: dict[str, dict[str, object]] = {}
    by_commit: dict[str, dict[str, object]] = {}
    for document in stored:
        identity = document.get("id")
        if not isinstance(identity, str):
            raise AdmissionError("operation record has no identity")
        if identity in by_id:
            raise AdmissionError("operation identity is recorded twice")
        by_id[identity] = document
        proof = document.get("proof")
        if document.get("status") != "completed" or not isinstance(proof, dict):
            continue
        commit = proof.get("commit")
        if isinstance(commit, str):
            by_commit[commit] = document
    return OperationIndex(by_id, by_commit)


def _reject_duplicate_proofs(documents: Sequence[Mapping[str, object]]) -> None:
    claimed: dict[str, Mapping[str, object]] = {}
    for document in documents:
        proof = document.get("proof")
        if document.get("status") != "completed" or not isinstance(proof, dict):
            continue
        commit = proof.get("commit")
        if not isinstance(commit, str):
            raise AdmissionError("completed operation has no commit")
        previous = claimed.get(commit)
        if previous is not None and previous != document:
            raise AdmissionError("conflicting operation proofs claim one commit")
        claimed[commit] = document


def load_index(repository: Path) -> OperationIndex:
    with _lock(repository) as root:
        _ensure_horizon(repository, root)
        documents = _documents(root)
    _reject_duplicate_proofs(documents)
    # An admission bind is already judging one record. Sync and scope reads need
    # the other stored records, not another pass through that same bind.
    if _binding_ids.get():
        return _operation_index(documents)
    return _operation_index(validate_operation(repository, document) for document in documents)


def _intent_document(intent: OperationIntent) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": intent.identity(),
        "kind": intent.kind,
        "status": "pending",
        "message": intent.message,
        "branch": intent.branch,
        "before": intent.before,
        "source": intent.source,
        "base": intent.base,
        "attested_base": intent.attested_base,
        "parents": list(intent.parents),
        "sync_kind": intent.sync_kind,
        "previous_base": intent.previous_base,
        "member": intent.member,
        "plans": list(intent.plans),
        "ready_evidence": intent.ready_evidence,
        "ready_evidence_sha256": intent.ready_evidence_sha256,
        "patch_id": intent.patch_id,
        "tree": intent.tree,
        "mappings": [list(pair) for pair in intent.mappings],
        "proof": None,
    }


def _same_intent(document: Mapping[str, object], intent: OperationIntent) -> bool:
    expected = _intent_document(intent)
    ignored = {"status", "proof"}
    comparable = {key: document.get(key) for key in expected if key not in ignored}
    return comparable == {key: value for key, value in expected.items() if key not in ignored}


def _completed_proof_matches_git(repository: Path, document: Mapping[str, object]) -> bool:
    proof = _proof_document(document)
    if proof is None:
        return False
    commit = proof.get("commit")
    if not isinstance(commit, str):
        return False
    try:
        actual = git_proof(repository, commit)
    except AdmissionError:
        return False
    return (
        actual["parents"] == proof.get("parents")
        and actual["tree"] == proof.get("tree")
        and actual["message"] == document.get("message")
    )


def begin_operation(repository: Path, intent: OperationIntent) -> dict[str, object]:
    """Persist pending intent. The same intent retries; a different one refuses.

    A completed proof that matches its Git object is idempotent. A different
    message may not create another commit. A pending operation with a different
    message fails closed.
    """

    document = _intent_document(intent)
    validate_operation(repository, document)
    with _lock(repository) as root:
        _ensure_horizon(repository, root)
        for stored in _documents(root):
            other = validate_operation(repository, stored)
            if (
                other.get("status") == "pending"
                and other.get("branch") == intent.branch
                and other.get("id") != intent.identity()
            ):
                raise AdmissionError(
                    "another operation is already pending for this branch",
                    expected="finish that operation before starting a different one on this branch",
                )
        path = _record_path(root, intent.identity())
        if path.exists():
            existing = _load_document(path)
            if _same_intent(existing, intent):
                return existing
            if _completed_proof_matches_git(repository, existing):
                return existing
            raise AdmissionError(
                "recorded operation conflicts with this request",
                expected="retry the same operation and message, or leave the recorded proof",
            )
        _write_atomic(path, _canonical(document))
        return document


def git_proof(repository: Path, commit: str) -> dict[str, object]:
    try:
        parents = git_output(repository, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        tree = git_output(repository, "rev-parse", f"{commit}^{{tree}}")
        message = commit_message(repository, commit)
    except GitError as error:
        raise AdmissionError(f"operation commit is unavailable: {error}") from error
    return {"commit": commit, "parents": parents, "tree": tree, "message": message}


def _proof_matches(document: Mapping[str, object], proof: Mapping[str, object]) -> bool:
    recorded = document.get("proof")
    keys = ("commit", "parents", "tree")
    return isinstance(recorded, dict) and all(recorded.get(key) == proof.get(key) for key in keys)


def complete_operation(repository: Path, intent: OperationIntent, commit: str) -> dict[str, object]:
    """Bind the pending intent to the commit Git actually created."""

    proof = git_proof(repository, commit)
    if proof["parents"] != list(intent.parents):
        raise AdmissionError("operation commit parents do not match the recorded intent")
    if proof["message"] != intent.message:
        raise AdmissionError("operation commit message does not match the recorded message")
    if intent.tree is not None and proof["tree"] != intent.tree:
        raise AdmissionError("operation commit tree does not match the recorded tree")
    stored = {"commit": proof["commit"], "parents": proof["parents"], "tree": proof["tree"]}
    with _lock(repository) as root:
        _ensure_horizon(repository, root)
        path = _record_path(root, intent.identity())
        if not path.exists():
            raise AdmissionError("operation completion has no pending intent")
        document = _load_document(path)
        if not _same_intent(document, intent):
            raise AdmissionError("operation completion conflicts with the recorded intent")
        if document.get("status") == "completed":
            if _proof_matches(document, stored):
                return document
            raise AdmissionError("completed operation proof conflicts with this commit")
        others = _documents(root)
        for other in others:
            other_proof = other.get("proof")
            if (
                other.get("id") != intent.identity()
                and isinstance(other_proof, dict)
                and other_proof.get("commit") == commit
            ):
                raise AdmissionError("another operation already proves this commit")
        document = {**document, "status": "completed", "proof": stored}
        validate_operation(repository, document)
        _write_atomic(path, _canonical(document))
        return document


def operation_for(repository: Path, intent: OperationIntent) -> dict[str, object] | None:
    with _lock(repository) as root:
        _ensure_horizon(repository, root)
        path = _record_path(root, intent.identity())
        if not path.exists():
            return None
        document = _load_document(path)
    if not _same_intent(document, intent):
        raise AdmissionError("recorded operation conflicts with this request")
    return document


def pending_message(repository: Path, branch: str, before: str, source: str) -> str | None:
    """The frozen message of a pending operation for this exact merge, if one exists."""

    index = load_index(repository)
    found = [
        document
        for document in index.by_id.values()
        if document.get("status") == "pending"
        and document.get("branch") == branch
        and document.get("before") == before
        and document.get("source") == source
    ]
    if not found:
        return None
    if len(found) != 1:
        raise AdmissionError("conflicting pending operations claim one merge")
    message = found[0].get("message")
    tree = found[0].get("tree")
    if not isinstance(message, str):
        raise AdmissionError("pending operation message is invalid")
    if tree is not None and not isinstance(tree, str):
        raise AdmissionError("pending operation tree is invalid")
    return message


def pending_tree(repository: Path, branch: str, before: str, source: str) -> str | None:
    index = load_index(repository)
    for document in index.by_id.values():
        if (
            document.get("status") == "pending"
            and document.get("branch") == branch
            and document.get("before") == before
            and document.get("source") == source
            and isinstance(document.get("tree"), str)
        ):
            return str(document["tree"])
    return None


def store_qualification(repository: Path, content: bytes) -> str:
    digest = _digest(content)
    with _lock(repository) as root:
        _ensure_horizon(repository, root)
        destination = _qualifications(root) / digest
        if destination.exists():
            try:
                existing = destination.read_bytes()
            except OSError as error:
                raise AdmissionError(
                    f"qualification bytes are unreadable: {destination.name}"
                ) from error
            if existing != content:
                raise AdmissionError("qualification bytes conflict with the recorded digest")
            return digest
        descriptor, temporary = tempfile.mkstemp(prefix=".qualification-", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return digest


def qualification_bytes(repository: Path, digest: str) -> bytes | None:
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return None
    path = state_root(repository) / "operations" / "qualifications" / digest
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if _digest(data) != digest:
        raise AdmissionError("stored qualification bytes do not match their digest")
    return data


def require_qualification(repository: Path, digest: str) -> None:
    if not digest:
        return
    if qualification_bytes(repository, digest) is None:
        raise AdmissionError("operation qualification bytes are missing")


def message_matches(repository: Path, commit: str, message: str) -> bool:
    try:
        return commit_message(repository, commit) == message
    except (GitError, AdmissionError):
        return False


def head_matches(repository: Path, intent: OperationIntent) -> str | None:
    """Return HEAD when it is already the recorded merge; refuse a different advance."""

    head = git_output(repository, "rev-parse", "HEAD")
    if head == intent.before:
        merge_head = run_git(repository, "rev-parse", "--verify", "MERGE_HEAD")
        if merge_head.returncode == 0:
            if merge_head.stdout.strip() != intent.source:
                raise AdmissionError("open merge does not match the recorded operation")
            return None
        return None
    proof = git_proof(repository, head)
    if proof["parents"] == list(intent.parents) and proof["message"] == intent.message:
        if intent.tree is None or proof["tree"] == intent.tree:
            return head
    raise AdmissionError(
        "branch advanced to a commit that does not match the recorded operation",
        expected="retry the same operation; do not create a second merge",
    )


def committer_environment(repository: Path, source: str) -> dict[str, str]:
    name = git_output(repository, "log", "-1", "--format=%cn", source)
    email = git_output(repository, "log", "-1", "--format=%ce", source)
    when = git_output(repository, "log", "-1", "--format=%cI", source)
    return {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_COMMITTER_DATE": when,
    }


def _commit_msg_hook(repository: Path) -> Path | None:
    configured = run_git(repository, "config", "--get", "core.hooksPath")
    if configured.returncode == 0 and configured.stdout.strip():
        directory = Path(configured.stdout.strip())
        if not directory.is_absolute():
            directory = (repository / directory).resolve()
    else:
        directory = repository_path(repository, "rev-parse", "--git-path", "hooks")
    hook = directory / "commit-msg"
    if hook.is_file() and os.access(hook, os.X_OK):
        return hook
    return None


def require_project_commit_message(repository: Path, message: str) -> None:
    """Run a project commit-msg hook before a commit Git itself would not check."""

    hook = _commit_msg_hook(repository)
    if hook is None:
        return
    directory = state_root(repository) / "operations"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".message-", dir=directory)
    path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(message.encode())
        completed = subprocess.run(  # noqa: S603  # nosec B603 -- project hook, message file only
            (str(hook), str(path)),
            cwd=repository,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode(errors="replace").strip()
            stdout = completed.stdout.decode(errors="replace").strip()
            diagnostic = stderr or stdout
            raise AdmissionError(diagnostic or "project commit message hook refused the message")
        if path.read_bytes() != message.encode():
            raise AdmissionError("project commit message hook changed the recorded message")
    finally:
        path.unlink(missing_ok=True)


def _restore_merge_message(repository: Path, message: str) -> None:
    """Leave the frozen bytes in MERGE_MSG.

    A conflicting merge appends conflict notes. ``git commit --no-edit`` would
    otherwise store those notes and miss the recorded message.
    """

    path = repository_path(repository, "rev-parse", "--git-path", "MERGE_MSG")
    try:
        path.write_bytes(message.encode())
    except OSError as error:
        raise AdmissionError(f"merge message is unwritable: {path.name}") from error


def write_message_copy(repository: Path, message: str) -> Path:
    directory = state_root(repository) / "operations"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".message-", dir=directory)
    path = Path(temporary)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(message.encode())
    return path


def create_commit(
    repository: Path,
    *,
    tree: str,
    parents: Sequence[str],
    message: str,
    identity: str,
) -> str:
    """Create one commit object. The same tree, parents, message, and identity repeat."""

    require_project_commit_message(repository, message)
    path = write_message_copy(repository, message)
    environment = {**os.environ, **committer_environment(repository, identity)}
    arguments = ["commit-tree", tree]
    for parent in parents:
        arguments.extend(("-p", parent))
    arguments.extend(("-F", str(path)))
    try:
        completed = run_git(repository, *arguments, environment=environment)
    finally:
        path.unlink(missing_ok=True)
    if completed.returncode != 0:
        raise AdmissionError(completed.stderr.strip() or "commit-tree failed")
    return completed.stdout.strip()


def _proof_document(document: Mapping[str, object]) -> dict[str, object] | None:
    proof = document.get("proof")
    if document.get("status") != "completed" or not isinstance(proof, dict):
        return None
    return proof


def require_bound_commit(repository: Path, document: Mapping[str, object]) -> dict[str, object]:
    """Refuse a completed record whose identity or Git object does not match."""

    validated = validate_operation(repository, document)
    if validated.get("status") != "completed":
        raise AdmissionError("operation is not complete")
    proof = validated.get("proof")
    if not isinstance(proof, dict):
        raise AdmissionError("operation is not complete")
    return proof


def attested_base_from(repository: Path, tip: str) -> str | None:
    """The newest base a verified operation or legacy commit attests."""

    index = load_index(repository)
    history = git_output(repository, "log", "--first-parent", "--format=%H", tip)
    for commit in history.splitlines():
        document = index.for_commit(commit)
        if document is None:
            document = bind_commit_if_pending(repository, commit)
        if document is not None:
            require_bound_commit(repository, document)
            attested = document.get("attested_base")
            if isinstance(attested, str) and attested:
                return attested
            raise AdmissionError("completed operation does not record its base")
        if not (legacy_commit(repository, commit) or legacy_pending_commit(repository, commit)):
            parents = git_output(repository, "rev-list", "--parents", "-n", "1", commit).split()[1:]
            if len(parents) > 1:
                raise AdmissionError("unrecorded merge cannot establish a baseline")
            continue
        message = commit_message(repository, commit)
        # Adopted history stays readable. Only exact old-engine text grants a base.
        if not legacy_proof_message(message):
            continue
        marker = re.search(r"^Signetum-Batch-Base:\s*(\S+)$", message, re.MULTILINE)
        if marker:
            return marker.group(1)
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AdmissionError("operation record list is invalid")
    return list(value)


def member_from_record(document: Mapping[str, object], commit: str, summary: str) -> dict[str, str]:
    if any(
        not isinstance(document.get(field), str) or document.get(field) == ""
        for field in ("member", "source")
    ):
        raise AdmissionError("admission record is missing its member")
    plans = _string_list(document.get("plans"))
    return {
        "branch": str(document["member"]),
        "original": str(document["source"]),
        "patch_id": str(document.get("patch_id") or ""),
        "ready_evidence": str(document.get("ready_evidence") or ""),
        "plan": ",".join(plans),
        "admission_commit": commit,
        "summary": summary,
    }


def batch_sync_record(document: Mapping[str, object]) -> tuple[str, str] | None:
    if document.get("kind") != "batch-sync":
        return None
    source = document.get("source")
    previous = document.get("previous_base")
    if not isinstance(source, str) or not isinstance(previous, str):
        raise AdmissionError("batch synchronization record is incomplete")
    return previous, source


def operation_input_names(repository: Path, base: str, tip: str) -> tuple[str, ...]:
    """Portable record and qualification names for commits in ``base..tip``."""

    index = load_index(repository)
    listed = set(
        filter(
            None,
            git_output(repository, "rev-list", "--first-parent", f"{base}..{tip}").splitlines(),
        )
    )
    names: list[str] = []
    for document in index.by_commit.values():
        proof = document.get("proof")
        if not isinstance(proof, dict) or proof.get("commit") not in listed:
            continue
        identity = document.get("id")
        if isinstance(identity, str):
            names.append(f"operations/records/{identity}.json")
        digest = document.get("ready_evidence_sha256")
        if isinstance(digest, str) and digest:
            names.append(f"operations/qualifications/{digest}")
    return tuple(sorted(names))


def _export_record(document: Mapping[str, object]) -> dict[str, object]:
    proof = require_bound_proof_shape(document)
    portable = {
        "schema_version": SCHEMA_VERSION,
        "id": document["id"],
        "kind": document["kind"],
        "message": document["message"],
        "branch": document["branch"],
        "before": document["before"],
        "source": document["source"],
        "base": document["base"],
        "attested_base": document["attested_base"],
        "parents": document["parents"],
        "sync_kind": document["sync_kind"],
        "previous_base": document["previous_base"],
        "member": document["member"],
        "plans": document["plans"],
        "ready_evidence": document["ready_evidence"],
        "ready_evidence_sha256": document["ready_evidence_sha256"],
        "patch_id": document["patch_id"],
        "tree": document["tree"],
        "mappings": _json_list(document.get("mappings") or [], "operation mappings are invalid"),
        "proof": proof,
    }
    _refuse_machine_paths(portable)
    return portable


def require_bound_proof_shape(document: Mapping[str, object]) -> dict[str, object]:
    proof = document.get("proof")
    if not isinstance(proof, dict):
        raise AdmissionError("only completed operations export")
    commit = proof.get("commit")
    parents = proof.get("parents")
    tree = proof.get("tree")
    if not isinstance(commit, str) or not isinstance(tree, str) or not isinstance(parents, list):
        raise AdmissionError("operation proof shape is invalid")
    return {"commit": commit, "parents": list(parents), "tree": tree}


def _refuse_machine_paths(value: object, location: str = "export") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"message", "content"}:
                continue
            _refuse_machine_paths(item, f"{location}.{key}")
        return
    if isinstance(value, list):
        for item in value:
            _refuse_machine_paths(item, location)
        return
    if not isinstance(value, str) or value == "":
        return
    if value.startswith(("/", "~")) or "\\" in value or ".." in Path(value).parts:
        raise AdmissionError(f"{location} depends on a machine path")


def export_operations(repository: Path, start: str, end: str) -> dict[str, object]:
    """Portable proof for commits reachable from ``end`` but not from ``start``."""

    try:
        commits = set(
            filter(
                None,
                git_output(repository, "rev-list", f"{start}..{end}").splitlines(),
            )
        )
    except GitError as error:
        raise AdmissionError(f"operation range is unavailable: {error}") from error
    index = load_index(repository)
    operations = []
    qualifications: dict[str, str] = {}
    for document in index.by_commit.values():
        proof = document.get("proof")
        if not isinstance(proof, dict) or proof.get("commit") not in commits:
            continue
        require_bound_commit(repository, document)
        operations.append(_export_record(document))
        digest = document.get("ready_evidence_sha256")
        if isinstance(digest, str) and digest:
            content = qualification_bytes(repository, digest)
            if content is None:
                raise AdmissionError("operation qualification bytes are missing")
            qualifications[digest] = content.decode("utf-8")
    operations.sort(key=lambda item: str(item["id"]))
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "operations": operations,
        "qualifications": [
            {"sha256": digest, "content": qualifications[digest]}
            for digest in sorted(qualifications)
        ],
    }
    horizon = _read_horizon(repository)
    if horizon is not None:
        adopted = horizon.get("adopted")
        document["legacy_horizon"] = {
            "schema_version": SCHEMA_VERSION,
            "adopted": adopted if adopted in {True, False} else False,
            "tips": horizon.get("tips"),
            "pending_merges": horizon.get("pending_merges"),
            "sync_record_sha256": horizon.get("sync_record_sha256"),
        }
    _refuse_machine_paths(document)
    return document


def _read_horizon(repository: Path) -> dict[str, object] | None:
    """Return the recorded horizon without creating one."""

    path = state_root(repository) / "operations" / "legacy-horizon.json"
    document = _read_json(path)
    if document is None:
        if path.exists():
            raise AdmissionError("legacy operation horizon is unreadable")
        return None
    if document.get("schema_version") != SCHEMA_VERSION:
        raise AdmissionError("legacy operation horizon is unreadable")
    return document


def _pending_merge_is_evidenced(
    repository: Path, item: Mapping[str, object], tips: Mapping[str, object]
) -> bool:
    """An imported pending merge must still be open or already inside an adopted tip."""

    before = item.get("before")
    source = item.get("source")
    trailers = item.get("trailers")
    if not isinstance(before, str) or not isinstance(source, str) or not isinstance(trailers, list):
        return False
    expected = tuple(sorted(str(line) for line in trailers))
    for _, checkout, _ in branch_checkouts(repository):
        head = run_git(checkout, "rev-parse", "--verify", "HEAD")
        merge_head = run_git(checkout, "rev-parse", "--verify", "MERGE_HEAD")
        if head.returncode != 0 or merge_head.returncode != 0:
            continue
        if head.stdout.strip() != before or merge_head.stdout.strip() != source:
            continue
        message_path = repository_path(checkout, "rev-parse", "--git-path", "MERGE_MSG")
        try:
            message = message_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if tuple(sorted(_trailer_lines(message))) == expected:
            return True
    for oid in tips.values():
        if not isinstance(oid, str):
            continue
        for merge in git_output(repository, "rev-list", "--merges", oid).splitlines():
            parents = git_output(repository, "rev-list", "--parents", "-n", "1", merge).split()[1:]
            if parents != [before, source]:
                continue
            if tuple(sorted(_trailer_lines(commit_message(repository, merge)))) == expected:
                return True
    return False


def _horizon_payload(document: Mapping[str, object]) -> dict[str, object] | None:
    horizon = document.get("legacy_horizon")
    if horizon is None:
        return None
    if (
        not isinstance(horizon, dict)
        or horizon.get("schema_version") != SCHEMA_VERSION
        or type(horizon.get("schema_version")) is not int
        or horizon.get("adopted") not in {True, False}
    ):
        raise AdmissionError("exported legacy horizon is invalid")
    tips = horizon.get("tips")
    pending = horizon.get("pending_merges")
    digests = horizon.get("sync_record_sha256")
    if not isinstance(tips, dict) or not isinstance(pending, list) or not isinstance(digests, list):
        raise AdmissionError("exported legacy horizon is invalid")
    _refuse_machine_paths(horizon, "legacy_horizon")
    return {
        "schema_version": SCHEMA_VERSION,
        "adopted": horizon.get("adopted") is True,
        "tips": dict(tips),
        "pending_merges": list(pending),
        "sync_record_sha256": list(digests),
    }


def _tip_commits(tips: Mapping[str, object]) -> tuple[str, ...]:
    commits: list[str] = []
    for oid in tips.values():
        if not isinstance(oid, str):
            raise AdmissionError("imported legacy horizon conflicts with the local horizon")
        commits.append(oid)
    return tuple(commits)


def _covered_by(repository: Path, commit: str, tips: Sequence[str]) -> bool:
    return any(commit == tip or _ancestor(repository, commit, tip) for tip in tips)


def _same_reachable_cutover(
    repository: Path, local: Sequence[str], incoming: Sequence[str]
) -> bool:
    """True when both tip sets reach exactly the same commits."""

    if not local and not incoming:
        return True
    if not local or not incoming:
        return False
    return all(_covered_by(repository, commit, local) for commit in incoming) and all(
        _covered_by(repository, commit, incoming) for commit in local
    )


def _cutover_expands(repository: Path, local: Sequence[str], incoming: Sequence[str]) -> bool:
    if not incoming:
        return False
    if not local:
        return True
    return any(not _covered_by(repository, commit, local) for commit in incoming)


def _require_compatible_cutover(
    repository: Path,
    existing: Mapping[str, object],
    horizon: Mapping[str, object],
    previous_tips: Mapping[str, object],
    tips: Mapping[str, object],
) -> bool:
    """Refuse a different cutover. True means the destination bytes stay.

    Adopt records one containing branch name. That label is not the authority:
    ``_in_horizon`` follows the tip commits. Equal commits must import even when
    the checkouts chose different branch names, and the destination record is
    not rewritten to the foreign names.
    """

    if horizon.get("adopted") is not True or existing.get("adopted") is not True:
        raise AdmissionError("imported legacy horizon conflicts with the local horizon")
    local_commits = _tip_commits(previous_tips)
    incoming_commits = _tip_commits(tips)
    if _same_reachable_cutover(repository, local_commits, incoming_commits):
        if existing.get("pending_merges") != horizon.get("pending_merges") or existing.get(
            "sync_record_sha256"
        ) != horizon.get("sync_record_sha256"):
            raise AdmissionError("imported legacy horizon conflicts with the local horizon")
        return True
    if _cutover_expands(repository, local_commits, incoming_commits):
        raise AdmissionError("imported legacy horizon cannot expand the recorded cutover")
    if set(tips) != set(previous_tips):
        raise AdmissionError("imported legacy horizon conflicts with the local horizon")
    for ref, oid in tips.items():
        previous = previous_tips.get(ref)
        if (
            not isinstance(previous, str)
            or not isinstance(oid, str)
            or (previous != oid and not _ancestor(repository, oid, previous))
        ):
            raise AdmissionError("imported legacy horizon cannot expand the recorded cutover")
    return False


def _accept_imported_horizon(
    repository: Path,
    root: Path,
    horizon: Mapping[str, object],
    *,
    modern: Sequence[str],
    write: bool = True,
) -> None:
    """Install a validated horizon without moving an existing cutover forward."""

    _validate_horizon_git(repository, horizon, modern=modern)
    tips = horizon.get("tips")
    pending = horizon.get("pending_merges")
    digests = horizon.get("sync_record_sha256")
    if not isinstance(tips, dict) or not isinstance(pending, list) or not isinstance(digests, list):
        raise AdmissionError("exported legacy horizon is invalid")
    local_digests = set(_sync_digests(root))
    path = root / "operations" / "legacy-horizon.json"
    existing = _read_json(path)
    if existing is None and path.exists():
        raise AdmissionError("legacy operation horizon is unreadable")
    if existing is not None and "adopted" not in existing:
        existing = {**existing, "adopted": False}
    recorded = existing.get("sync_record_sha256") if isinstance(existing, dict) else []
    allowed = local_digests | set(recorded if isinstance(recorded, list) else [])
    if any(not isinstance(item, str) or item not in allowed for item in digests):
        raise AdmissionError("imported sync evidence is not in this repository")
    evidenced_tips = tips if horizon.get("adopted") is True else {}
    for item in pending:
        evidenced = isinstance(item, dict) and _pending_merge_is_evidenced(
            repository, item, evidenced_tips
        )
        if isinstance(item, dict) and not evidenced:
            raise AdmissionError("imported legacy merge is not evidenced in this repository")
    # A checkout establishes its own cutover. Import may repeat that record; it
    # may not create one, including on a fresh clone or an unadopted horizon.
    if horizon.get("adopted") is True and not (
        isinstance(existing, dict) and existing.get("adopted") is True
    ):
        raise AdmissionError("imported legacy horizon cannot establish a cutover")
    if existing is None:
        if write:
            _write_atomic(path, _canonical(dict(horizon)))
        return
    if _canonical(existing) == _canonical(dict(horizon)):
        return
    previous_tips = existing.get("tips")
    unadopted_empty = (
        existing.get("adopted") is False and isinstance(previous_tips, dict) and not previous_tips
    )
    if not unadopted_empty:
        if not isinstance(previous_tips, dict):
            raise AdmissionError("imported legacy horizon conflicts with the local horizon")
        if _require_compatible_cutover(repository, existing, horizon, previous_tips, tips):
            return
    if write:
        _write_atomic(path, _canonical(dict(horizon)))


def import_operations(repository: Path, document: Mapping[str, object]) -> dict[str, object]:
    """Load portable proof. The same bundle is a no-op; a conflict writes nothing."""

    if document.get("schema_version") != SCHEMA_VERSION:
        raise AdmissionError("operation export schema is unsupported")
    operations = document.get("operations")
    qualifications = document.get("qualifications")
    if not isinstance(operations, list) or not isinstance(qualifications, list):
        raise AdmissionError("operation export is invalid")
    blobs: dict[str, bytes] = {}
    for item in qualifications:
        if not isinstance(item, dict):
            raise AdmissionError("qualification export is invalid")
        digest = item.get("sha256")
        content = item.get("content")
        if not isinstance(digest, str) or not isinstance(content, str):
            raise AdmissionError("qualification export is invalid")
        data = content.encode()
        if _digest(data) != digest:
            raise AdmissionError("qualification bytes do not match their digest")
        if digest in blobs and blobs[digest] != data:
            raise AdmissionError("qualification export conflicts")
        blobs[digest] = data
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    claimed: dict[str, dict[str, object]] = {}
    for item in operations:
        if not isinstance(item, dict):
            raise AdmissionError("operation export entry is invalid")
        _refuse_machine_paths(item)
        identity = item.get("id")
        if not isinstance(identity, str) or identity in seen:
            raise AdmissionError("operation export identity conflicts")
        seen.add(identity)
        proof = require_bound_proof_shape(item)
        commit = str(proof["commit"])
        try:
            actual = git_proof(repository, commit)
        except AdmissionError as error:
            raise AdmissionError(f"exported commit is not in this repository: {commit}") from error
        if actual["parents"] != proof["parents"] or actual["tree"] != proof["tree"]:
            raise AdmissionError("exported commit parents or tree do not match this repository")
        if actual["message"] != item.get("message"):
            raise AdmissionError("exported commit message does not match this repository")
        digest = item.get("ready_evidence_sha256")
        if isinstance(digest, str) and digest:
            if digest not in blobs:
                raise AdmissionError("exported qualification bytes are missing")
        elif digest not in ("", None):
            raise AdmissionError("exported qualification identity is invalid")
        candidate = {**item, "schema_version": SCHEMA_VERSION, "status": "completed"}
        validate_operation(
            repository,
            {key: value for key, value in candidate.items() if key != "status"},
            portable=True,
            qualifications=blobs,
        )
        proof_commit = str(proof["commit"])
        previous = claimed.get(proof_commit)
        if previous is not None and previous != candidate:
            raise AdmissionError("conflicting operation proofs claim one commit")
        claimed[proof_commit] = candidate
        normalized.append(candidate)
    horizon = _horizon_payload(document)
    with _lock(repository) as root:
        modern = _proof_commits(root)
        for item in normalized:
            proof = item.get("proof")
            if not isinstance(proof, dict):
                continue
            commit = proof.get("commit")
            if isinstance(commit, str):
                modern.append(commit)
        if horizon is not None:
            _accept_imported_horizon(repository, root, horizon, modern=modern, write=False)
        local_commits: dict[str, str] = {}
        for existing in _documents(root):
            proof = existing.get("proof")
            if existing.get("status") != "completed" or not isinstance(proof, dict):
                continue
            commit = proof.get("commit")
            identity = existing.get("id")
            if isinstance(commit, str) and isinstance(identity, str):
                local_commits[commit] = identity
        for item in normalized:
            path = _record_path(root, str(item["id"]))
            proof = item.get("proof")
            commit = proof.get("commit") if isinstance(proof, dict) else None
            if (
                isinstance(commit, str)
                and commit in local_commits
                and local_commits[commit] != item.get("id")
            ):
                raise AdmissionError("conflicting operation proofs claim one commit")
            incoming = {**item, "schema_version": SCHEMA_VERSION, "status": "completed"}
            if path.exists():
                existing = _load_document(path)
                if _canonical(_export_record(existing)) != _canonical(_export_record(incoming)):
                    raise AdmissionError("imported operation conflicts with the local record")
                continue
        for digest, content in blobs.items():
            destination = _qualifications(root) / digest
            if destination.exists() and destination.read_bytes() != content:
                raise AdmissionError("imported qualification conflicts with local bytes")
        for digest, content in blobs.items():
            destination = _qualifications(root) / digest
            if not destination.exists():
                store_outside = content
                descriptor, temporary = tempfile.mkstemp(
                    prefix=".qualification-", dir=destination.parent
                )
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(store_outside)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, destination)
                finally:
                    Path(temporary).unlink(missing_ok=True)
        for item in normalized:
            path = _record_path(root, str(item["id"]))
            if path.exists():
                continue
            _write_atomic(
                path,
                _canonical({**item, "schema_version": SCHEMA_VERSION, "status": "completed"}),
            )
        if horizon is not None:
            _accept_imported_horizon(repository, root, horizon, modern=modern)
    return {"schema_version": SCHEMA_VERSION, "status": "imported", "operations": len(normalized)}


@dataclass(frozen=True)
class MergeOutcome:
    """Result of creating or resuming one recorded merge."""

    status: str
    commit: str


def intent_from_document(document: Mapping[str, object]) -> OperationIntent:
    """Rebuild the intent that was frozen in a record."""

    def text(name: str) -> str:
        value = document.get(name)
        if not isinstance(value, str):
            raise AdmissionError(f"operation record field is invalid: {name}")
        return value

    def optional(name: str) -> str | None:
        value = document.get(name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise AdmissionError(f"operation record field is invalid: {name}")
        return value

    parents = document.get("parents")
    plans = document.get("plans")
    tree = document.get("tree")
    sync_kind = document.get("sync_kind")
    if not isinstance(parents, list) or not all(isinstance(item, str) for item in parents):
        raise AdmissionError("operation parents are invalid")
    if not isinstance(plans, list) or not all(isinstance(item, str) for item in plans):
        raise AdmissionError("operation plans are invalid")
    if tree is not None and not isinstance(tree, str):
        raise AdmissionError("operation tree is invalid")
    if sync_kind is not None and not isinstance(sync_kind, str):
        raise AdmissionError("operation sync kind is invalid")
    return OperationIntent(
        kind=text("kind"),
        branch=text("branch"),
        before=text("before"),
        source=text("source"),
        base=text("base"),
        message=text("message"),
        attested_base=text("attested_base"),
        parents=tuple(parents),
        sync_kind=sync_kind,
        previous_base=optional("previous_base"),
        member=optional("member"),
        plans=tuple(plans),
        ready_evidence=(
            text("ready_evidence") if isinstance(document.get("ready_evidence"), str) else ""
        ),
        ready_evidence_sha256=(
            text("ready_evidence_sha256")
            if isinstance(document.get("ready_evidence_sha256"), str)
            else ""
        ),
        patch_id=text("patch_id") if isinstance(document.get("patch_id"), str) else "",
        tree=tree if isinstance(tree, str) else None,
        mappings=_mapping_pairs(document.get("mappings") or []),
    )


def _commit_matches_document(repository: Path, commit: str, document: Mapping[str, object]) -> bool:
    try:
        proof = git_proof(repository, commit)
    except AdmissionError:
        return False
    parents = document.get("parents")
    if proof["parents"] != parents or proof["message"] != document.get("message"):
        return False
    tree = document.get("tree")
    return not isinstance(tree, str) or proof["tree"] == tree


def _matching_records(repository: Path, intent: OperationIntent) -> list[dict[str, object]]:
    index = load_index(repository)
    found = []
    for document in index.by_id.values():
        if (
            document.get("kind") == intent.kind
            and document.get("branch") == intent.branch
            and document.get("source") == intent.source
            and document.get("base") == intent.base
            and document.get("sync_kind") == intent.sync_kind
        ):
            found.append(document)
    return found


def remember_continuation(
    repository: Path, intent: OperationIntent, messages: Sequence[str]
) -> None:
    """Keep frozen messages for members an interrupted admission still owes."""

    frozen = [freeze_message(message) for message in messages]
    with _lock(repository) as root:
        path = _record_path(root, intent.identity())
        if not path.exists():
            raise AdmissionError("continuation has no pending operation")
        document = _load_document(path)
        if document.get("status") != "pending" or not _same_intent(document, intent):
            raise AdmissionError("continuation conflicts with the recorded operation")
        document["continuation_messages"] = frozen
        _write_atomic(path, _canonical(document))


def continuation_messages(repository: Path, commit: str) -> tuple[str, ...] | None:
    """Messages frozen for members after ``commit``, when this engine stored them."""

    document = load_index(repository).for_commit(commit)
    if document is None or "continuation_messages" not in document:
        return None
    messages = document.get("continuation_messages")
    if not isinstance(messages, list) or not all(isinstance(item, str) for item in messages):
        raise AdmissionError("stored continuation messages are invalid")
    return tuple(messages)


def bind_commit_if_pending(repository: Path, commit: str) -> dict[str, object] | None:
    """Bind a pending record when ``commit`` is already the recorded Git object."""

    matches = [
        document
        for document in load_index(repository).by_id.values()
        if document.get("status") == "pending"
        and _commit_matches_document(repository, commit, document)
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise AdmissionError("conflicting pending operations claim one commit")
    return complete_operation(repository, intent_from_document(matches[0]), commit)


def _resume_completed_merge(
    repository: Path, document: Mapping[str, object], head: str
) -> MergeOutcome:
    """Move to the recorded commit when HEAD is still its first parent.

    A completed proof that is not on HEAD does not authorize another merge.
    Fast-forward only while the branch is still the recorded parent and the
    existing commit's parents are that parent plus the recorded source.
    """

    proof = document.get("proof")
    if not isinstance(proof, dict) or not isinstance(proof.get("commit"), str):
        raise AdmissionError("operation is not complete")
    commit = str(proof["commit"])
    before = document.get("before")
    source = document.get("source")
    if head == before and isinstance(source, str):
        actual = git_proof(repository, commit)
        if actual["parents"] == [head, source]:
            completed = run_git(repository, "merge", "--ff-only", commit)
            if completed.returncode != 0:
                raise AdmissionError(completed.stderr.strip() or "cannot resume the recorded merge")
            moved = git_output(repository, "rev-parse", "HEAD")
            if moved != commit:
                raise AdmissionError("resumed merge does not match the recorded commit")
            return MergeOutcome("recovered", commit)
    raise AdmissionError(
        "completed operation for this source is not on the branch",
        expected="retry from the recorded commit; do not create a second merge",
    )


def merge_operation(repository: Path, intent: OperationIntent, *, recovery: str) -> MergeOutcome:
    """Create or resume one merge and bind it to the commit Git actually stored.

    ``contained`` means the source is already in HEAD and no record needed binding.
    ``completed`` means an earlier proof already covers HEAD. ``recovered`` binds a
    commit that existed before this call. ``created`` is the merge this call made.
    """

    frozen = {**_intent_document(intent), "message": freeze_message(intent.message)}
    intent = intent_from_document(frozen)
    head = git_output(repository, "rev-parse", "HEAD")
    done: list[tuple[str, str]] = []
    ready: list[dict[str, object]] = []
    outside: list[dict[str, object]] = []
    for document in _matching_records(repository, intent):
        if document.get("status") == "completed":
            proof = require_bound_commit(repository, document)
            commit = str(proof["commit"])
            if commit == head or _ancestor(repository, commit, head):
                done.append(("completed", commit))
            else:
                outside.append(document)
            continue
        if document.get("status") != "pending":
            raise AdmissionError("operation status is invalid")
        if _commit_matches_document(repository, head, document):
            complete_operation(repository, intent_from_document(document), head)
            done.append(("recovered", head))
            continue
        if head != document.get("before"):
            raise AdmissionError(
                "pending operation does not match the branch tip",
                expected=recovery,
            )
        if document.get("message") != intent.message or not _same_intent(document, intent):
            if document.get("before") != intent.before:
                raise AdmissionError(
                    "pending operation does not match the branch tip",
                    expected=recovery,
                )
            raise AdmissionError(
                "recorded operation conflicts with this request",
                expected="retry the same operation and message, or leave the recorded proof",
            )
        ready.append(document)
    overlapped = (done and ready) or (done and outside) or (ready and outside)
    if len(done) > 1 or len(ready) > 1 or len(outside) > 1 or overlapped:
        raise AdmissionError("conflicting operation proofs claim one merge")
    if done:
        status, commit = done[0]
        return MergeOutcome(status, commit)
    if outside:
        return _resume_completed_merge(repository, outside[0], head)
    if _ancestor(repository, intent.source, head) and not ready:
        return MergeOutcome("contained", head)
    if ready:
        intent = intent_from_document(ready[0])
    else:
        if head != intent.before:
            raise AdmissionError("operation before does not match the branch tip")
        begin_operation(repository, intent)
    require_project_commit_message(repository, intent.message)
    merge_head = run_git(repository, "rev-parse", "--verify", "MERGE_HEAD")
    if merge_head.returncode == 0:
        if merge_head.stdout.strip() != intent.source:
            raise AdmissionError("open merge does not match the recorded operation")
        _restore_merge_message(repository, intent.message)
        raise MergeConflict("merge is unresolved", expected=recovery)
    path = write_message_copy(repository, intent.message)
    try:
        completed = run_git(
            repository,
            "-c",
            "merge.log=false",
            "merge",
            "--no-ff",
            intent.source,
            "-F",
            str(path),
        )
    finally:
        path.unlink(missing_ok=True)
    if completed.returncode:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        if git_output(repository, "diff", "--name-only", "--diff-filter=U"):
            _restore_merge_message(repository, intent.message)
            raise MergeConflict(diagnostic or "merge is unresolved", expected=recovery)
        raise OperationFailed(diagnostic or "merge failed")
    merged = git_output(repository, "rev-parse", "HEAD")
    if not _commit_matches_document(repository, merged, _intent_document(intent)):
        raise AdmissionError("merge result does not match the recorded operation")
    complete_operation(repository, intent, merged)
    return MergeOutcome("created", merged)


def commit_operation(repository: Path, intent: OperationIntent) -> str:
    """Create or reuse one commit object and bind its proof. Does not move a branch."""

    frozen = {**_intent_document(intent), "message": freeze_message(intent.message)}
    intent = intent_from_document(frozen)
    if intent.tree is None:
        raise AdmissionError("commit operation requires a tree")
    document = begin_operation(repository, intent)
    if document.get("status") == "completed":
        proof = require_bound_commit(repository, document)
        return str(proof["commit"])
    stored = intent_from_document(document)
    head = git_output(repository, "rev-parse", "HEAD")
    if _commit_matches_document(repository, head, document):
        complete_operation(repository, stored, head)
        return head
    if head != stored.before and not _ancestor(repository, stored.before, head):
        raise AdmissionError("operation before does not match the branch tip")
    created = create_commit(
        repository,
        tree=str(stored.tree),
        parents=stored.parents,
        message=stored.message,
        identity=stored.source,
    )
    complete_operation(repository, stored, created)
    return created


def legacy_publication_commit(
    repository: Path, commit: str, target_branch: str, base: str, tip: str
) -> bool:
    """True when ``commit`` is retained old publication evidence, not a copied trailer."""

    if not (legacy_commit(repository, commit) or legacy_pending_commit(repository, commit)):
        return False
    try:
        parents = git_output(repository, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        tree = git_output(repository, "rev-parse", f"{commit}^{{tree}}")
        source_tree = git_output(repository, "rev-parse", f"{tip}^{{tree}}")
        message = commit_message(repository, commit)
    except (GitError, AdmissionError):
        return False
    text = message if message.endswith("\n") else f"{message}\n"
    if parents != [base, tip] or tree != source_tree or not _legacy_merge_message(text):
        return False
    subject, _, _rest = text.partition("\n")
    trailers = {
        line.split(":", 1)[0]: line.split(":", 1)[1].strip()
        for line in _trailer_lines(text)
        if ":" in line
    }
    return (
        subject.startswith("Merge ")
        and subject.endswith(f" into {target_branch}")
        and trailers.get("Signetum-Batch-Base") == base
        and trailers.get("Signetum-Batch-Tip") == tip
        and "Signetum-Member" not in trailers
    )


def record_decision_mapping(
    repository: Path, commit: str, base: str, directory: str, message: str
) -> dict[str, object]:
    """Bind a human numbering commit to the approved change basis.

    The commit and its message already exist. This records that operation; it
    does not create another commit or a second decision ledger.
    """

    frozen = freeze_message(message)
    if _trailer_lines(frozen):
        raise AdmissionError("operation message cannot carry Signetum trailers")
    try:
        resolved = git_output(repository, "rev-parse", f"{commit}^{{commit}}")
    except GitError as error:
        raise AdmissionError(f"decision mapping commit is unavailable: {commit}") from error
    if commit_message(repository, resolved) != frozen:
        raise AdmissionError("decision mapping message does not match the commit")
    proof = git_proof(repository, resolved)
    parents = proof["parents"]
    if not isinstance(parents, list) or len(parents) != 1:
        raise AdmissionError("decision mapping commit must have one parent")
    before = str(parents[0])
    if not _ancestor(repository, base, before):
        raise AdmissionError("decision mapping is not bound to the approved base")
    mappings = _numbering_mappings(repository, before, resolved, directory)
    if not mappings:
        raise AdmissionError("decision mapping does not match the committed rename")
    head = git_output(repository, "rev-parse", "HEAD")
    if resolved != head and not _ancestor(repository, resolved, head):
        raise AdmissionError("decision mapping commit is not on this branch")
    intent = OperationIntent(
        kind="decision-mapping",
        branch=branch_name(repository),
        before=before,
        source=resolved,
        base=base,
        message=frozen,
        attested_base=base,
        parents=(before,),
        tree=str(proof["tree"]),
        mappings=mappings,
    )
    begin_operation(repository, intent)
    return complete_operation(repository, intent, resolved)


def engine_accepts_message_file(engine: Path) -> bool:
    """True when the engine at ``engine`` can take ``--message-file`` on admission."""

    if not (engine / "signetum" / "lifecycle.py").is_file():
        return False
    script = """
import sys
sys.path.insert(0, sys.argv[1])
from signetum.lifecycle import _parser
parser = _parser()
for action in parser._actions:
    choices = getattr(action, "choices", None)
    if not isinstance(choices, dict) or "batch-admit" not in choices:
        continue
    raise SystemExit(0 if "--message-file" in choices["batch-admit"].format_help() else 1)
raise SystemExit(1)
"""
    completed = subprocess.run(  # noqa: S603  # nosec B603 -- local interpreter, engine path only
        (sys.executable, "-I", "-B", "-c", script, str(engine)),
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _running_engine_repository() -> Path:
    engine = Path(__file__).resolve().parents[1]
    try:
        return Path(git_output(engine, "rev-parse", "--show-toplevel"))
    except GitError as error:
        raise AdmissionError(
            "repository engine adoption refuses an engine outside a repository"
        ) from error


def _path_blob(repository: Path, commit: str, path: str) -> str | None:
    completed = run_git(repository, "rev-parse", "--verify", "-q", f"{commit}:{path}")
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _inside_engine(path: str) -> bool:
    return path == _ENGINE_TREE or path.startswith(f"{_ENGINE_TREE}/")


def _repo_relative(base: Path, value: str) -> str | None:
    if Path(value).is_absolute():
        return None
    parts: list[str] = []
    for part in (*base.parts, *Path(value).parts):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _lock_binds_engine(lock_path: str, text: str) -> bool:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise AdmissionError(
            f"engine handoff source lockfile is unreadable: {lock_path}"
        ) from error
    found = False

    def walk(node: object, key: str | None = None) -> None:
        nonlocal found
        if isinstance(node, dict):
            for child_key, child in node.items():
                walk(child, child_key if isinstance(child_key, str) else None)
        elif isinstance(node, list):
            for child in node:
                walk(child, key)
        elif isinstance(node, str) and key in _LOCK_SOURCE_KEYS:
            relative = _repo_relative(Path(lock_path).parent, node)
            if relative is not None and _inside_engine(relative):
                found = True

    try:
        walk(data)
    except RecursionError as error:
        raise AdmissionError(
            f"engine handoff source lockfile is unreadable: {lock_path}"
        ) from error
    return found


def _source_text(repository: Path, source: str, path: str) -> str | None:
    completed = run_git(repository, "show", f"{source}:{path}")
    if completed.returncode != 0:
        return None
    return completed.stdout


def _preparation_bindings(repository: Path, source: str) -> tuple[str, ...]:
    """Lockfiles that bind the engine, plus the uv manifest each such lock binds.

    Declared lockfiles come from the source manifest. The engine tree already
    carries lockfiles inside itself. A missing manifest means there is nothing
    further to carry. Historical engine-only proofs do not call this.
    """

    manifest_text = _source_text(repository, source, "signetum.toml")
    if manifest_text is None:
        return ()
    # manifest imports the validation graph. Load it only while discovering inputs.
    from signetum.manifest import ManifestError, parse_manifest  # noqa: PLC0415

    try:
        manifest = parse_manifest(manifest_text)
    except ManifestError as error:
        raise AdmissionError(f"engine handoff source manifest is unreadable: {error}") from error
    bindings: list[str] = []
    for lock in manifest.repository.lockfiles:
        if _inside_engine(lock):
            continue
        lock_text = _source_text(repository, source, lock)
        if lock_text is None:
            raise AdmissionError(f"engine handoff source is missing a declared lockfile: {lock}")
        if not _lock_binds_engine(lock, lock_text):
            continue
        bindings.append(lock)
        if Path(lock).name != "uv.lock":
            raise AdmissionError(
                "engine handoff cannot check the declared preparation bundle: " + lock,
                expected="bind the repository engine with a uv.lock this operation can check",
            )
        project = (Path(lock).parent / "pyproject.toml").as_posix()
        if _inside_engine(project):
            continue
        if _source_text(repository, source, project) is None:
            raise AdmissionError(
                f"engine handoff source is missing the project manifest for {lock}"
            )
        bindings.append(project)
    return tuple(sorted(set(bindings)))


def _safe_archive_target(root: Path, name: str) -> Path:
    if not name or name.startswith(("/", "\\")) or "\\" in name:
        raise AdmissionError("engine handoff source archive escapes its directory")
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise AdmissionError("engine handoff source archive escapes its directory")
    target = (root / candidate).resolve()
    if not target.is_relative_to(root.resolve()):
        raise AdmissionError("engine handoff source archive escapes its directory")
    return target


def _extract_git_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            target = _safe_archive_target(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise AdmissionError("engine handoff source archive contains an unexpected member")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = bundle.extractfile(member)
            if extracted is None:
                raise AdmissionError("engine handoff source archive is unreadable")
            with extracted:
                target.write_bytes(extracted.read())


def _require_coherent_preparation(repository: Path, source: str, bindings: Sequence[str]) -> None:
    """Refuse a source whose declared uv project and lock do not match, before effects."""

    locks = [path for path in bindings if Path(path).name == "uv.lock"]
    if not locks:
        return
    uv = shutil.which("uv")
    if uv is None:
        raise AdmissionError(
            "engine handoff cannot check the declared preparation bundle",
            expected="install uv and retry adopt-repository-engine",
        )
    directory = state_root(repository) / "operations"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".bundle-", dir=directory) as temporary:
        root = Path(temporary)
        archive = root / "source.tar"
        tree = root / "tree"
        completed = run_git(
            repository,
            "archive",
            "--output",
            str(archive),
            source,
            "--",
            _ENGINE_TREE,
            *bindings,
        )
        if completed.returncode != 0:
            raise AdmissionError(completed.stderr.strip() or "engine handoff source archive failed")
        _extract_git_archive(archive, tree)
        for lock in locks:
            project = tree / Path(lock).parent
            if not (project / "pyproject.toml").is_file() or not (project / "uv.lock").is_file():
                raise AdmissionError(
                    f"engine handoff source is missing the project manifest for {lock}"
                )
            checked = subprocess.run(  # noqa: S603  # nosec B603 -- resolved uv, lock check only
                (uv, "lock", "--check", "--offline"),
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )
            if checked.returncode != 0:
                diagnostic = (checked.stderr or checked.stdout).strip()
                detail = f": {diagnostic}" if diagnostic else ""
                raise AdmissionError(
                    "engine handoff source preparation bundle does not match its lock" + detail,
                    expected=(
                        "ready a commit whose declared manifest and lock match the repository "
                        "engine, then retry adopt-repository-engine"
                    ),
                )


def _preparation_bundle_matches(repository: Path, source: str, bindings: Sequence[str]) -> bool:
    if _path_blob(repository, "HEAD", _ENGINE_TREE) != _path_blob(repository, source, _ENGINE_TREE):
        return False
    return all(
        _path_blob(repository, "HEAD", path) == _path_blob(repository, source, path)
        for path in bindings
    )


def _binding_cacheinfo(repository: Path, source: str, path: str) -> tuple[str, str]:
    completed = run_git(repository, "ls-tree", source, "--", path)
    line = completed.stdout.strip()
    meta, separator, name = line.partition("\t")
    parts = meta.split()
    if completed.returncode != 0 or not separator or name != path or len(parts) != 3:
        raise AdmissionError(f"engine handoff source preparation input is unreadable: {path}")
    if parts[1] != "blob":
        raise AdmissionError(f"engine handoff source preparation input is unreadable: {path}")
    return parts[0], parts[2]


def _replaced_engine_tree(
    repository: Path, before: str, source: str, bindings: Sequence[str] = ()
) -> str:
    try:
        source_tree = git_output(repository, "rev-parse", f"{source}:{_ENGINE_TREE}")
    except GitError as error:
        raise AdmissionError("engine handoff source has no repository engine") from error
    directory = state_root(repository) / "operations"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".index-", dir=directory)
    os.close(descriptor)
    index = Path(temporary)
    # An empty placeholder is not a Git index. read-tree creates the real one.
    index.unlink()
    try:
        for arguments in (
            ("read-tree", before),
            ("rm", "-r", "--cached", "--ignore-unmatch", "--", _ENGINE_TREE),
            ("read-tree", f"--prefix={_ENGINE_TREE}/", source_tree),
        ):
            completed = run_git(repository, *arguments, index_file=index)
            if completed.returncode != 0:
                raise AdmissionError(completed.stderr.strip() or "engine handoff tree failed")
        for path in bindings:
            mode, blob = _binding_cacheinfo(repository, source, path)
            updated = run_git(
                repository,
                "update-index",
                "--add",
                "--cacheinfo",
                f"{mode},{blob},{path}",
                index_file=index,
            )
            if updated.returncode != 0:
                raise AdmissionError(updated.stderr.strip() or "engine handoff tree failed")
        written = run_git(repository, "write-tree", index_file=index)
        if written.returncode != 0:
            raise AdmissionError(written.stderr.strip() or "engine handoff tree failed")
        return written.stdout.strip()
    finally:
        index.unlink(missing_ok=True)


def _handoff_result(
    batch: Path, record: WorkspaceRecord, created: str, source: str
) -> dict[str, object]:
    pinned = read_record(state_root(batch), branch_name(batch)).engine
    if pinned is None or pinned.source != "repository" or pinned != record.engine:
        raise AdmissionError("engine handoff changed the batch engine pin")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "adopted",
        "commit": created,
        "source": source,
    }


def _recorded_engine_handoff(
    batch: Path, *, source: str, message: str, base: str, branch: str
) -> dict[str, object] | None:
    """A completed handoff for this exact source and message, if one exists."""

    index = load_index(batch)
    head = git_output(batch, "rev-parse", "HEAD")
    current = index.for_commit(head)
    if (
        isinstance(current, dict)
        and current.get("kind") == "engine-handoff"
        and current.get("status") == "completed"
        and current.get("source") == source
        and current.get("message") == message
        and current.get("base") == base
        and current.get("branch") == branch
    ):
        return current
    for document in index.by_id.values():
        proof = document.get("proof")
        if (
            document.get("kind") == "engine-handoff"
            and document.get("status") == "completed"
            and document.get("source") == source
            and document.get("message") == message
            and document.get("base") == base
            and document.get("branch") == branch
            and document.get("before") == head
            and isinstance(proof, dict)
            and isinstance(proof.get("commit"), str)
        ):
            return document
    return None


def _advance_recorded_handoff(batch: Path, document: Mapping[str, object]) -> str:
    proof = document.get("proof")
    if not isinstance(proof, dict) or not isinstance(proof.get("commit"), str):
        raise AdmissionError("engine handoff did not advance the batch to the recorded commit")
    created = str(proof["commit"])
    if git_output(batch, "rev-parse", "HEAD") != created:
        moved = run_git(batch, "merge", "--ff-only", created)
        if moved.returncode != 0:
            raise AdmissionError(
                moved.stderr.strip() or "engine handoff could not advance the batch"
            )
    if git_output(batch, "rev-parse", "HEAD") != created:
        raise AdmissionError("engine handoff did not advance the batch to the recorded commit")
    return created


def _member_at_source(repository: Path, source: str) -> tuple[Path, WorkspaceRecord]:
    """The registered member workspace whose tip is ``source``."""

    inventory = git_output(repository, "worktree", "list", "--porcelain", strip=False)
    for block in inventory.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, separator, value = line.partition(" ")
            if separator:
                fields[key] = value
        branch = fields.get("branch", "").removeprefix("refs/heads/")
        if fields.get("HEAD") != source or not branch or "worktree" not in fields:
            continue
        try:
            record = read_record(state_root(repository), branch)
        except WorkspaceError:
            continue
        if record.kind == "member":
            return Path(fields["worktree"]), record
    raise AdmissionError(
        "engine handoff source is not an approved ready member",
        expected=(
            "ready the approved member that contains this repository engine, then retry "
            "adopt-repository-engine"
        ),
    )


def adopt_repository_engine(
    batch: Path, message: str, source_commit: str | None = None
) -> dict[str, object]:
    """Copy this repository engine and the preparation inputs it needs.

    The source must be an approved Ready member tip. Declared lockfiles that bind
    the engine, and the uv project manifest those locks bind, travel with the
    engine tree. Other application paths stay behind. The caller message is stored
    on the handoff commit. The batch pin stays ``repository``. A completed handoff
    for the same source and message is reused, including when the checked-out
    engine already accepts message files, and is not rewritten. A later message
    and Ready source continue when the checked-out preparation bundle does not
    match. Accepting a message file is not that match. The installed engine is
    not changed.
    """

    frozen = freeze_message(message)
    if _trailer_lines(frozen):
        raise AdmissionError("operation message cannot carry Signetum trailers")
    record = read_record(state_root(batch), branch_name(batch))
    if record.kind != "batch" or record.engine is None or record.engine.source != "repository":
        raise AdmissionError(
            "repository engine adoption requires a repository-pinned batch",
            expected=(
                "open the batch with the repository engine, then retry adopt-repository-engine"
            ),
        )
    engine_repository = _running_engine_repository()
    if state_root(engine_repository) != state_root(batch):
        raise AdmissionError(
            "repository engine adoption refuses an engine from another checkout",
            expected=(
                "run maintenance adopt-repository-engine from the repository engine "
                "inside this Git repository"
            ),
        )
    if source_commit is None:
        source = git_output(engine_repository, "rev-parse", "HEAD")
    else:
        try:
            source = git_output(batch, "rev-parse", f"{source_commit}^{{commit}}")
        except GitError as error:
            raise AdmissionError(
                f"engine handoff source is unavailable: {source_commit}"
            ) from error
    engine_status = git_output(
        engine_repository, "status", "--porcelain", "--", "skills/signetum/scripts/engine"
    )
    if engine_status.strip():
        raise AdmissionError("running repository engine does not match the source commit")
    compared = run_git(
        engine_repository, "diff", "--quiet", source, "--", "skills/signetum/scripts/engine"
    )
    if compared.returncode != 0:
        raise AdmissionError("running repository engine does not match the source commit")
    if not isinstance(record.base, str) or not record.base:
        raise AdmissionError("batch has no recorded base")
    branch = branch_name(batch)
    recorded = _recorded_engine_handoff(
        batch, source=source, message=frozen, base=record.base, branch=branch
    )
    if recorded is not None:
        created = _advance_recorded_handoff(batch, recorded)
        return _handoff_result(batch, record, created, source)
    bindings = _preparation_bindings(batch, source)
    # lifecycle imports this module. Handoff checks stay with admission evidence
    # so scope and lifecycle are not imported while this module is loading.
    from signetum.lifecycle import (  # noqa: PLC0415
        _qualify_engine_source,
        _require_handoff_authorization,
    )

    _qualify_engine_source(batch, source)
    before = git_output(batch, "rev-parse", "HEAD")
    _require_handoff_authorization(batch, record, before)
    if run_git(batch, "status", "--porcelain").stdout.strip():
        raise AdmissionError("repository engine adoption requires a clean batch")
    # Message-file support does not prove the preparation bundle matches.
    if _preparation_bundle_matches(batch, source, bindings) and engine_accepts_message_file(
        batch / _ENGINE_TREE
    ):
        raise AdmissionError("batch engine already accepts message files")
    _require_coherent_preparation(batch, source, bindings)
    tree = _replaced_engine_tree(batch, before, source, bindings)
    intent = OperationIntent(
        kind="engine-handoff",
        branch=branch,
        before=before,
        source=source,
        base=record.base,
        message=frozen,
        attested_base=record.base,
        parents=(before,),
        tree=tree,
    )
    created = commit_operation(batch, intent)
    if git_output(batch, "rev-parse", "HEAD") == before:
        moved = run_git(batch, "merge", "--ff-only", created)
        if moved.returncode != 0:
            raise AdmissionError(
                moved.stderr.strip() or "engine handoff could not advance the batch"
            )
    if git_output(batch, "rev-parse", "HEAD") != created:
        raise AdmissionError("engine handoff did not advance the batch to the recorded commit")
    return _handoff_result(batch, record, created, source)


def evidence_sha256(repository: Path, receipt_root: Path, name: str) -> str:
    path = receipt_root / name
    if Path(name).name != name or not path.is_file():
        raise AdmissionError("ready evidence path is invalid")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise AdmissionError(f"ready evidence is unreadable: {error}") from error
    return store_qualification(repository, content)
