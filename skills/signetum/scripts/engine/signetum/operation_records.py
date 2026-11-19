"""Versioned local operations: one authority for sync, admission, and publication.

Pending intent is stored before Git effects. Completion binds the actual commit,
its parents, and its tree, and the record is validated completely when it is
written. Reads parse the stored records; a record is checked against Git where
it is used. The records stay local to this repository: anyone able to forge them
could already rewrite its refs, so they guard against interrupted writes and
against a manual merge or copied message posing as an operation.

Retained history from before the first structured operation stays readable
through the old engine's exact merge text. Once an operation is an ancestor, a
later commit cannot fall back to message proof. Work an older engine left
pending finishes with that engine.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess  # nosec B404 -- explicit argument vectors, never a shell
import tempfile
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from signetum.git import GitError, git_output, repository_path, run_git
from signetum.operations import AdmissionError, MergeConflict, OperationFailed
from signetum.workspaces import (
    branch_checkouts,
    branch_name,
    state_root,
)

SCHEMA_VERSION = 1
# Qualification reads the operation index while completion already holds _lock.
# A second flock in the same process never returns, so the holding thread re-enters.
_lock_depth = threading.local()
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
MERGE_KINDS = frozenset({"member-sync", "batch-sync", "admission", "publication"})
_TRAILER = re.compile(r"^Signetum-", re.IGNORECASE)
_OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
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


def require_project_commit_messages(repository: Path, messages: Sequence[str]) -> None:
    """Refuse a message the project's commit-msg hook rejects, before any effect or record."""

    for message in messages:
        require_project_commit_message(repository, freeze_message(message))


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


def _ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    completed = run_git(repository, "merge-base", "--is-ancestor", ancestor, descendant)
    if completed.returncode not in (0, 1):
        raise AdmissionError(completed.stderr.strip() or "cannot compare history")
    return completed.returncode == 0


def legacy_commit(repository: Path, commit: str) -> bool:
    """True when ``commit`` predates every structured operation on its history.

    Old-engine text is readable only there: once a structured operation is an
    ancestor, a later commit cannot fall back to message proof.
    """

    index = load_index(repository)
    if commit in index.by_commit:
        return False
    return not any(
        proof == commit or _ancestor(repository, proof, commit) for proof in index.by_commit
    )


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


def _text(document: Mapping[str, object], name: str, *, optional: bool = False) -> str | None:
    value = document.get(name)
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise AdmissionError(f"operation record is malformed: {name}")
    return value


def parse_operation(document: object) -> dict[str, object]:
    """The shape of one stored record. Git identity is judged where it is used."""

    if not isinstance(document, Mapping):
        raise AdmissionError("operation record is malformed")
    unknown = set(document) - _LOCAL_FIELDS
    if unknown:
        raise AdmissionError(f"operation record has unknown fields: {', '.join(sorted(unknown))}")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or type(document["schema_version"]) is not int
    ):
        raise AdmissionError("operation record schema is unsupported")
    if document.get("kind") not in KINDS:
        raise AdmissionError(f"operation kind is invalid: {document.get('kind')}")
    status = document.get("status")
    if status not in {"pending", "completed"}:
        raise AdmissionError("operation status is invalid")
    for name in ("before", "source", "base", "attested_base"):
        _oid(document.get(name), name)
    for name in ("previous_base", "tree"):
        if document.get(name) is not None:
            _oid(document.get(name), name)
    message = _text(document, "message")
    if message != freeze_message(str(message)) or _trailer_lines(str(message)):
        raise AdmissionError("operation message is invalid")
    _text(document, "branch")
    _text(document, "member", optional=True)
    parents = document.get("parents")
    if not isinstance(parents, list) or not parents or parents[0] != document["before"]:
        raise AdmissionError("operation parents are invalid")
    for item in parents:
        _oid(item, "parent")
    plans = document.get("plans", [])
    if not isinstance(plans, list) or not all(isinstance(item, str) for item in plans):
        raise AdmissionError("operation record is malformed: plans")
    sync_kind = document.get("sync_kind")
    if sync_kind is not None and sync_kind not in SYNC_KINDS:
        raise AdmissionError("operation sync kind is invalid")
    if "mappings" not in document:
        raise AdmissionError("operation record is malformed: mappings")
    _mapping_pairs(document["mappings"])
    for name in ("ready_evidence", "ready_evidence_sha256", "patch_id"):
        if not isinstance(document.get(name, ""), str):
            raise AdmissionError(f"operation record is malformed: {name}")
    digest = document.get("ready_evidence_sha256") or ""
    if digest and _SHA256.fullmatch(str(digest)) is None:
        raise AdmissionError("operation qualification identity is invalid")
    continuation = document.get("continuation_messages")
    if continuation is not None and (
        not isinstance(continuation, list)
        or not all(isinstance(item, str) for item in continuation)
    ):
        raise AdmissionError("stored continuation messages are invalid")
    proof = document.get("proof")
    if status == "pending":
        if proof is not None:
            raise AdmissionError("pending operation cannot carry proof")
    elif (
        not isinstance(proof, dict)
        or set(proof) != {"commit", "parents", "tree"}
        or proof.get("parents") != parents
    ):
        raise AdmissionError("operation proof shape is invalid")
    else:
        _oid(proof.get("commit"), "proof commit")
        _oid(proof.get("tree"), "proof tree")
    expected = intent_from_document(document).identity()
    if expected != document.get("id"):
        raise AdmissionError("operation identity does not match its fields")
    return dict(document)


def _require_kind(repository: Path, document: Mapping[str, object]) -> None:
    """The relations a new record must hold when it is written."""

    kind = document["kind"]
    before, source, base = str(document["before"]), str(document["source"]), str(document["base"])
    attested = document["attested_base"]
    parents = document["parents"]
    member, previous = document.get("member"), document.get("previous_base")
    sync_kind, mappings = document.get("sync_kind"), document.get("mappings")
    tree = document.get("tree")
    if kind in MERGE_KINDS:
        if parents != [before, source] or source == before:
            raise AdmissionError("operation source is not its second parent")
        if not _ancestor(repository, base, before) or not _ancestor(repository, base, source):
            raise AdmissionError("operation base is not an ancestor of the merge")
    else:
        if parents != [before] or source == before or not isinstance(tree, str):
            raise AdmissionError(f"{kind} record is invalid")
        if not _ancestor(repository, base, before):
            raise AdmissionError(f"{kind} is not bound to its base")
    valid = {
        "member-sync": sync_kind is not None and attested == base,
        "batch-sync": sync_kind is None and previous == base and attested == source,
        "admission": sync_kind is None
        and isinstance(member, str)
        and attested == base
        and bool(document.get("ready_evidence_sha256"))
        and bool(document.get("patch_id")),
        "publication": sync_kind is None and attested == base == before and isinstance(tree, str),
        "decision-mapping": sync_kind is None and attested == base and bool(mappings),
        "engine-handoff": sync_kind is None and attested == base,
    }[str(kind)]
    if not valid or (kind != "admission" and member is not None):
        raise AdmissionError(f"{kind} record is invalid")
    if kind not in {"member-sync", "batch-sync"} and previous is not None:
        raise AdmissionError(f"{kind} record is invalid")
    if kind not in {"member-sync", "decision-mapping"} and mappings:
        raise AdmissionError(f"{kind} record is invalid")
    if kind == "publication" and tree != git_output(repository, "rev-parse", f"{source}^{{tree}}"):
        raise AdmissionError("publication tree is not the published source tree")
    if kind == "decision-mapping":
        directory = str(Path(_mapping_pairs(mappings)[0][0]).parent)
        if _numbering_mappings(repository, before, source, directory) != _mapping_pairs(mappings):
            raise AdmissionError("decision mapping does not match the committed rename")


def validate_operation(repository: Path, document: Mapping[str, object]) -> dict[str, object]:
    """A record about to be written: its shape, relations and Git objects."""

    parsed = parse_operation(document)
    _require_kind(repository, parsed)
    if parsed["status"] == "completed":
        require_bound_commit(repository, parsed)
    digest = str(parsed.get("ready_evidence_sha256") or "")
    if digest:
        require_qualification(repository, digest)
    return parsed


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
    by_id: dict[str, dict[str, object]] = {}
    by_commit: dict[str, dict[str, object]] = {}
    for document in documents:
        identity = str(document["id"])
        if identity in by_id:
            raise AdmissionError("operation identity is recorded twice")
        by_id[identity] = dict(document)
        proof = document.get("proof")
        if document.get("status") != "completed" or not isinstance(proof, dict):
            continue
        commit = str(proof["commit"])
        if commit in by_commit:
            raise AdmissionError("conflicting operation proofs claim one commit")
        by_commit[commit] = by_id[identity]
    return OperationIndex(by_id, by_commit)


def load_index(repository: Path) -> OperationIndex:
    """Stored records, parsed. Each was validated against Git when it was written."""

    with _lock(repository) as root:
        documents = _documents(root)
    return _operation_index(parse_operation(document) for document in documents)


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
        _discard_unfinishable(repository, root)
        for stored in _documents(root):
            other = parse_operation(stored)
            if (
                other.get("status") == "pending"
                and other.get("branch") == intent.branch
                and other.get("id") != intent.identity()
            ):
                if _pending_is_stale(repository, other):
                    _record_path(root, str(other["id"])).unlink(missing_ok=True)
                    continue
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
            if _only_message_differs(existing, intent) and not _commit_matches_document(
                repository, git_output(repository, "rev-parse", "HEAD"), existing
            ):
                require_project_commit_message(repository, intent.message)
                path.unlink()
                _write_atomic(path, _canonical(document))
                return document
            if _pending_is_stale(repository, existing):
                # Left by an operation that never took effect, such as an abandoned workspace.
                path.unlink()
                _write_atomic(path, _canonical(document))
                return document
            raise AdmissionError(
                "recorded operation conflicts with this request",
                expected="retry the same operation and message, or leave the recorded proof",
            )
        # A message the project would refuse can never become a commit, so it never
        # becomes pending intent either.
        require_project_commit_message(repository, intent.message)
        _write_atomic(path, _canonical(document))
        return document


def _only_message_differs(document: Mapping[str, object], intent: OperationIntent) -> bool:
    """A pending record that produced no commit and differs from the request only by message."""

    if document.get("status") != "pending" or not isinstance(document.get("message"), str):
        return False
    same = {**_intent_document(intent), "message": document["message"]}
    return _same_intent(document, intent_from_document(same))


def _replace_pending_message(
    repository: Path, document: Mapping[str, object], message: str
) -> dict[str, object]:
    """Let the operator correct the message of an operation that produced no commit."""

    with _lock(repository) as root:
        path = _record_path(root, str(document["id"]))
        replaced = {**dict(document), "message": message}
        validate_operation(repository, replaced)
        _write_atomic(path, _canonical(replaced))
    return replaced


def _pending_is_stale(repository: Path, document: Mapping[str, object]) -> bool:
    """Pending intent that can no longer take effect and produced no commit.

    Its branch or checkout is gone, or its checkout is back at the recorded
    starting point with no merge open, so retrying simply begins again.
    """

    if document.get("status") != "pending":
        return False
    branch = document.get("branch")
    if not isinstance(branch, str):
        return False
    checkout = next(
        (path for name, path, _ in branch_checkouts(repository) if name == branch), None
    )
    if checkout is None or not checkout.is_dir():
        return True
    if run_git(checkout, "rev-parse", "--verify", "--quiet", "MERGE_HEAD").returncode == 0:
        return False
    head = git_output(checkout, "rev-parse", "HEAD")
    return not _commit_matches_document(repository, head, document)


def retire_pending_operations(repository: Path, branch: str) -> list[dict[str, object]]:
    """Remove every pending operation record of a branch and return their summaries.

    An abandoned or removed workspace never completes them; the caller keeps the
    summaries in the workspace's retirement record as the audit trail.
    """

    retired: list[dict[str, object]] = []
    with _lock(repository) as root:
        for stored in _documents(root):
            if stored.get("status") == "pending" and stored.get("branch") == branch:
                retired.append(
                    {
                        key: stored.get(key)
                        for key in ("id", "kind", "before", "source", "base", "status")
                    }
                )
                _record_path(root, str(stored["id"])).unlink(missing_ok=True)
    return retired


def _discard_unfinishable(repository: Path, root: Path) -> None:
    """Drop pending intent whose message the project's commit-msg hook refuses.

    An earlier engine recorded intent before that check. Such a record cannot
    produce a commit, so it only blocks a retry with a corrected message.
    """

    for stored in _documents(root):
        other = parse_operation(stored)
        message = other.get("message")
        if other.get("status") != "pending" or not isinstance(message, str):
            continue
        try:
            require_project_commit_message(repository, message)
        except AdmissionError:
            _record_path(root, str(other["id"])).unlink(missing_ok=True)


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
    """Refuse a completed record whose Git object does not match where it is used."""

    parsed = parse_operation(document)
    proof = parsed.get("proof")
    if parsed.get("status") != "completed" or not isinstance(proof, dict):
        raise AdmissionError("operation is not complete")
    actual = git_proof(repository, str(proof["commit"]))
    if (
        actual["parents"] != proof["parents"]
        or actual["tree"] != proof["tree"]
        or actual["message"] != parsed["message"]
    ):
        raise AdmissionError("operation proof does not match the Git object")
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
        if not legacy_commit(repository, commit):
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


@dataclass(frozen=True)
class MergeOutcome:
    """Result of creating or resuming one recorded merge."""

    status: str
    commit: str


def intent_from_document(document: Mapping[str, object]) -> OperationIntent:
    """Rebuild the intent frozen in a record whose field types parse_operation checked."""

    def optional(name: str) -> str | None:
        value = document.get(name)
        return None if value is None else str(value)

    return OperationIntent(
        kind=str(document["kind"]),
        branch=str(document["branch"]),
        before=str(document["before"]),
        source=str(document["source"]),
        base=str(document["base"]),
        message=str(document["message"]),
        attested_base=str(document["attested_base"]),
        parents=tuple(str(item) for item in _string_list(document["parents"])),
        sync_kind=optional("sync_kind"),
        previous_base=optional("previous_base"),
        member=optional("member"),
        plans=tuple(_string_list(document.get("plans", []))),
        ready_evidence=str(document.get("ready_evidence") or ""),
        ready_evidence_sha256=str(document.get("ready_evidence_sha256") or ""),
        patch_id=str(document.get("patch_id") or ""),
        tree=optional("tree"),
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
        if document.get("message") != intent.message and _only_message_differs(document, intent):
            # Nothing was committed, so the operator may supply a corrected message.
            require_project_commit_message(repository, intent.message)
            document = _replace_pending_message(repository, document, intent.message)
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
        if git_output(repository, "diff", "--name-only", "--diff-filter=U"):
            raise MergeConflict("merge is unresolved", expected=recovery)
        # A clean merge the commit-msg hook refused: commit it with the recorded message,
        # which the hook now judges together with the actual staged change.
        return _commit_open_merge(repository, intent)
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
        if run_git(repository, "rev-parse", "--verify", "MERGE_HEAD").returncode == 0:
            _restore_merge_message(repository, intent.message)
            raise OperationFailed(
                diagnostic or "merge failed",
                expected="rerun the operation with a corrected --message-file; nothing was "
                "committed and the recorded message is replaced",
            )
        raise OperationFailed(diagnostic or "merge failed")
    merged = git_output(repository, "rev-parse", "HEAD")
    if not _commit_matches_document(repository, merged, _intent_document(intent)):
        raise AdmissionError("merge result does not match the recorded operation")
    complete_operation(repository, intent, merged)
    return MergeOutcome("created", merged)


def _commit_open_merge(repository: Path, intent: OperationIntent) -> MergeOutcome:
    path = write_message_copy(repository, intent.message)
    try:
        completed = run_git(repository, "commit", "-F", str(path))
    finally:
        path.unlink(missing_ok=True)
    if completed.returncode:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        _restore_merge_message(repository, intent.message)
        raise OperationFailed(
            diagnostic or "merge commit failed",
            expected="rerun the operation with a corrected --message-file; nothing was "
            "committed and the recorded message is replaced",
        )
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


def evidence_sha256(repository: Path, receipt_root: Path, name: str) -> str:
    path = receipt_root / name
    if Path(name).name != name or not path.is_file():
        raise AdmissionError("ready evidence path is invalid")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise AdmissionError(f"ready evidence is unreadable: {error}") from error
    return store_qualification(repository, content)
