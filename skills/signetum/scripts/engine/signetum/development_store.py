"""Approval-bound source journal mutations and read-only current decision views."""

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TypedDict

from signetum.change.models import (
    DecisionStatus,
    complete_decision_replacements,
    require_relative_path,
)
from signetum.change_record import ChangeRecord, contract_digest, parse_change_record
from signetum.development_log import (
    ApprovalProof,
    DevelopmentEntry,
    DevelopmentSnapshot,
    DevelopmentTransaction,
    project_development_history,
    resolution_index,
    validate_transaction,
    withdrawn_resolution_ids,
)
from signetum.git import git_output, repository_path, run_git
from signetum.serialization import contract_mapping, dataclass_from_mapping, load_json
from signetum.source_authority import (
    authority_roots,
    committed_blob,
    committed_blob_identity,
    require_accepted_decision,
    require_ancestor,
    require_committed_bindings,
    source_path,
)
from signetum.traceability.loading import parse_decision
from signetum.workspaces import claim_change, read_record


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def parse_request(value: object) -> DevelopmentTransaction:
    transaction = dataclass_from_mapping(DevelopmentTransaction, value, use_defaults=True)
    validate_transaction(transaction)
    return transaction


def approved_authority(
    repository: Path, change_id: str, commit: str, *, approved: bool = True
) -> tuple[ChangeRecord, ApprovalProof]:
    root, _ = authority_roots(repository, commit=commit, historical=True)
    relative = f"{root}/{change_id}/change.toml"
    blob = committed_blob(repository, commit, relative)
    if blob is None:
        raise ValueError(f"committed change authority is absent: {relative}")
    record = parse_change_record(blob[1])
    if record.id != change_id or record.status != "active":
        raise ValueError("journal requires an active owning change record")
    if approved and record.approval is None:
        raise ValueError("journal requires committed human-confirmed approval")
    require_ancestor(repository, record.contract.approved_base, commit)
    return record, ApprovalProof(commit=commit, path=relative, blob=blob[0])


def _validate_payload(
    repository: Path, transaction: DevelopmentTransaction, record: ChangeRecord, commit: str
) -> None:
    if transaction.approval_digest != contract_digest(record.contract):
        raise ValueError("development request approval changed; review the approved contract again")
    requirements = {item.id for item in record.contract.requirements}
    for observation in transaction.observations:
        if not set(observation.requirements) <= requirements:
            raise ValueError("observation names a requirement outside its approved change")
    approved = {item.id: item for item in record.contract.decisions}
    if len(approved) != len(record.contract.decisions):
        raise ValueError("approved decision transaction identities are not unique")
    retirements = {item.id: item for item in record.contract.retirements}
    if len(retirements) != len(record.contract.retirements):
        raise ValueError("approved evidence retirement identities are not unique")
    for retirement in transaction.retirements:
        if retirements.get(retirement.id) != retirement:
            raise ValueError("evidence retirement differs from its exact approved proposal")
    for decision in transaction.decisions:
        _, decision_root = authority_roots(repository, commit=commit, historical=True)
        if approved.get(decision.id) != decision:
            raise ValueError("decision transaction differs from its exact approved proposal")
        change_root, _ = authority_roots(repository, commit=commit, historical=True)
        acceptance = f"{change_root}/{record.id}/change.toml#decisions/{decision.id}"
        if decision.authority == acceptance:
            continue
        require_accepted_decision(repository, commit, decision.authority, decision_root)


def _read_journal(
    repository: Path,
    relative: str,
    head: str,
    authorities: dict[tuple[str, str], tuple[ChangeRecord, ApprovalProof]],
) -> tuple[bytes, tuple[DevelopmentEntry, ...]]:
    path = source_path(repository, relative)
    committed = committed_blob(repository, head, relative)
    if not path.is_file():
        raise ValueError(f"development journal is missing: {relative}")
    data = path.read_bytes()
    if committed is not None and not data.startswith(committed[1].encode()):
        raise ValueError("committed development history cannot be rewritten")
    prefix = b""
    entries = []
    change_id = path.parent.name
    for number, line in enumerate(data.splitlines(keepends=True), 1):
        if not line.endswith(b"\n") or not line.strip():
            raise ValueError("development journal contains an incomplete record")
        entry = dataclass_from_mapping(DevelopmentEntry, load_json(line.decode()))
        validate_transaction(entry.transaction, judge_resolutions=False)
        if (
            entry.sequence != number
            or entry.previous_digest != _digest(prefix)
            or entry.transaction.change_id != change_id
        ):
            raise ValueError("development journal chain or owning change is invalid")
        require_ancestor(repository, entry.approval.commit, head)
        key = change_id, entry.approval.commit
        if key not in authorities:
            authorities[key] = approved_authority(repository, *key)
        record, proof = authorities[key]
        if proof != entry.approval:
            raise ValueError("journal historical approval blob does not match")
        _validate_payload(repository, entry.transaction, record, entry.approval.commit)
        entries.append(entry)
        prefix += line
    return data, tuple(entries)


def _journals(repository: Path, head: str) -> tuple[str, ...]:
    root, _ = authority_roots(repository, commit=head)
    source_path(repository, root)
    committed = git_output(repository, "ls-tree", "-r", "--name-only", "-z", head, "--", root)
    names = {
        name
        for name in committed.split("\0")
        if name.endswith("/events.jsonl") and PurePosixPath(name).parent.parent.as_posix() == root
    }
    names.update(
        path.relative_to(repository).as_posix()
        for path in (repository / root).glob("*/events.jsonl")
    )
    return tuple(sorted(names))


@dataclass(frozen=True)
class _SourceHistory:
    head: str
    history_digest: str
    entries: tuple[DevelopmentEntry, ...]
    authorities: dict[tuple[str, str], tuple[ChangeRecord, ApprovalProof]]


def read_sources(repository: Path) -> _SourceHistory:
    repository = repository.resolve()
    head = git_output(repository, "rev-parse", "HEAD")
    entries = []
    inputs = []
    authorities: dict[tuple[str, str], tuple[ChangeRecord, ApprovalProof]] = {}
    for relative in _journals(repository, head):
        data, values = _read_journal(repository, relative, head, authorities)
        inputs.append((relative, _digest(data)))
        entries.extend(values)
    if git_output(repository, "rev-parse", "HEAD") != head:
        raise ValueError("source commit changed while reading development history")
    return _SourceHistory(head, _digest(_json(inputs)), tuple(entries), authorities)


def judge_sources(repository: Path, sources: _SourceHistory) -> DevelopmentSnapshot:
    result = project_development_history(sources.entries, sources.history_digest)
    standing = frozenset(item.resolution.id for item in result.observations if item.resolution)
    for entry in sources.entries:
        record, _ = sources.authorities[(entry.transaction.change_id, entry.approval.commit)]
        _resolution_targets(
            repository,
            entry.transaction,
            sources.entries,
            record,
            entry.approval.commit,
            historical=True,
            standing=standing,
        )
    return result


def snapshot(repository: Path) -> DevelopmentSnapshot:
    """Judge standing answers after withdrawals; reading never writes source."""
    return judge_sources(repository, read_sources(repository))


class DevelopmentReviewError(ValueError):
    """Frozen source review cannot establish its retained execution evidence."""


class SourceReviewInputs(TypedDict):
    commit: str
    history_digest: str
    journals: dict[str, str]
    changes: list[str]
    decision_transactions: list[str]


def _review_sources(
    repository: Path, change_ids: tuple[str, ...], commit: str
) -> tuple[SourceReviewInputs, DevelopmentSnapshot]:
    try:
        sources = read_sources(repository)
        if sources.head != commit:
            raise ValueError("source review commit differs from the current frozen source")
        require_committed_bindings(repository, commit)
        journals: dict[str, str] = {}
        identities = []
        for relative in _journals(repository, commit):
            blob = committed_blob(repository, commit, relative)
            if blob is None or source_path(repository, relative).read_bytes() != blob[1].encode():
                raise ValueError("source review requires committed development journals")
            journals[relative] = blob[0]
            identities.append((relative, _digest(blob[1].encode())))
        if _digest(_json(identities)) != sources.history_digest:
            raise ValueError("source journals changed during review")
        result = judge_sources(repository, sources)
        recorded = {
            decision.id: decision
            for entry in result.entries
            for decision in entry.transaction.decisions
        }
        root, _ = authority_roots(repository, commit=commit)
        selected = []
        for change_id in sorted(set(change_ids)):
            blob = committed_blob(repository, commit, f"{root}/{change_id}/change.toml")
            if blob is None:
                continue
            record = parse_change_record(blob[1])
            if record.id != change_id:
                raise ValueError("source review change identity is inconsistent")
            for decision in record.contract.decisions:
                if recorded.get(decision.id) != decision:
                    raise ValueError(
                        f"approved decision is absent from source history: {decision.id}"
                    )
            selected.append(change_id)
        decisions = sorted(
            decision.id
            for entry in result.entries
            if entry.transaction.change_id in selected
            for decision in entry.transaction.decisions
        )
        return {
            "commit": commit,
            "history_digest": sources.history_digest,
            "journals": journals,
            "changes": selected,
            "decision_transactions": decisions,
        }, result
    except (OSError, ValueError) as error:
        raise DevelopmentReviewError(str(error)) from error


def review_inputs(
    repository: Path, change_ids: tuple[str, ...], *, commit: str
) -> SourceReviewInputs:
    """Bind exact committed journals and their accepted decision dependencies."""
    return _review_sources(repository, change_ids, commit)[0]


def decision_application_commits(
    repository: Path, change_ids: tuple[str, ...], commits: tuple[str, ...], *, commit: str
) -> frozenset[str]:
    """Identify own commits introducing exact current approved decision applications.

    Ordinary observations and re-appended old history are not implementation.
    The existing source reviewer remains the approval and journal verifier.
    """
    inputs, result = _review_sources(repository, change_ids, commit)
    root, _ = authority_roots(repository, commit=commit)
    candidates: dict[str, set[str]] = {}
    for change_id in inputs["changes"]:
        record, _ = approved_authority(repository, change_id, commit)
        digest = contract_digest(record.contract)
        lines = {
            _json(contract_mapping(entry)).decode()
            for entry in result.entries
            if entry.transaction.change_id == change_id
            and entry.transaction.approval_digest == digest
            and entry.transaction.decisions
        }
        if lines:
            candidates[f"{root}/{change_id}/events.jsonl"] = lines
    applications = set()
    for revision in commits:
        for relative, lines in candidates.items():
            current = committed_blob(repository, revision, relative)
            if current is None:
                continue
            previous = committed_blob(repository, f"{revision}^", relative)
            added = set(current[1].splitlines()) - (
                set(previous[1].splitlines()) if previous else set()
            )
            if added & lines:
                applications.add(revision)
    return frozenset(applications)


def reconciliation_summary(
    repository: Path, change_ids: tuple[str, ...], *, commit: str
) -> dict[str, object]:
    """Project selected standing discoveries; validation never appends an event."""
    inputs, result = _review_sources(repository, change_ids, commit)
    affected = {
        action.target
        for entry in result.entries
        if entry.transaction.change_id in inputs["changes"]
        for action in (
            *entry.transaction.resolutions,
            *entry.transaction.retractions,
            *entry.transaction.retirements,
        )
    }
    states = tuple(
        item
        for item in result.observations
        if item.change_id in inputs["changes"] or item.observation.id in affected
    )
    pending = [item.observation.id for item in states if item.status == "pending"]
    if pending:
        raise DevelopmentReviewError("unresolved source observations: " + ", ".join(pending))
    try:
        for state in states:
            for evidence in state.effective_evidence:
                if committed_blob_identity(repository, commit, evidence) is None:
                    raise ValueError(
                        f"standing resolution evidence is absent from reviewed source: {evidence}"
                    )
            if state.resolution is not None and state.resolution.status == "deferred":
                change, _, requirement = (state.resolution.followup or "").partition("#")
                following, _ = approved_authority(repository, change, commit, approved=False)
                if requirement not in {item.id for item in following.contract.requirements}:
                    raise ValueError("standing deferral has no active follow-up requirement")
    except (OSError, ValueError) as error:
        raise DevelopmentReviewError(str(error)) from error
    return {
        "schema_version": 1,
        "observation_count": len(states),
        "decision_transactions": inputs["decision_transactions"],
        "changes": [
            {
                "change_id": change,
                "observations": [
                    {
                        "id": item.observation.id,
                        "requirements": list(item.observation.requirements),
                        "summary": item.observation.summary,
                        "status": item.status,
                        "reason": item.resolution.reason if item.resolution else None,
                        "evidence": list(item.effective_evidence),
                        "source_event": item.source_event,
                        "approval": contract_mapping(item.approval),
                        "resolution_event": item.resolution_event,
                        "retractions": [contract_mapping(value) for value in item.retractions],
                        "retirements": [contract_mapping(value) for value in item.retirements],
                    }
                    for item in states
                    if item.change_id == change
                ],
            }
            for change in sorted(set(inputs["changes"]) | {item.change_id for item in states})
        ],
    }


@contextmanager
def _writer(repository: Path) -> Iterator[Path]:
    common = repository_path(repository, "rev-parse", "--git-common-dir")
    root = common / "signetum"
    root.mkdir(parents=True, exist_ok=True)
    with (root / "development.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another development journal writer is active") from error
        try:
            yield root
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _resolution_targets(
    repository: Path,
    transaction: DevelopmentTransaction,
    entries: tuple[DevelopmentEntry, ...],
    record: ChangeRecord,
    commit: str,
    *,
    historical: bool = False,
    standing: frozenset[str] | None = None,
) -> None:
    observed = {item.id: item for entry in entries for item in entry.transaction.observations}
    resolutions = resolution_index(entries)
    withdrawn = withdrawn_resolution_ids(entries)
    for resolution in transaction.resolutions:
        if standing is not None and resolution.id not in standing:
            continue
        for evidence in resolution.evidence:
            require_relative_path(evidence)
            if not historical and not source_path(repository, evidence).is_file():
                raise ValueError(f"acceptance evidence target is absent: {evidence}")
        if resolution.status == "deferred":
            change_id, separator, requirement = (resolution.followup or "").partition("#")
            if not separator or change_id == transaction.change_id:
                raise ValueError("deferral requires another active follow-up change requirement")
            following, _ = approved_authority(repository, change_id, commit, approved=False)
            if requirement not in {item.id for item in following.contract.requirements}:
                raise ValueError("follow-up requirement is absent")
            original = observed.get(resolution.target)
            transfers = {item.id: item.target for item in record.contract.transferred}
            target = f"{change_id}/{requirement}"
            if original is None or any(
                transfers.get(identity) != target for identity in original.requirements
            ):
                raise ValueError("deferral requires the exact human-approved requirement transfer")
    if not historical:
        for retraction in transaction.retractions:
            previous = resolutions.get(retraction.resolution_id)
            if (
                previous is None
                or previous.target != retraction.target
                or retraction.resolution_id in withdrawn
            ):
                raise ValueError("retraction requires an exact standing resolution")
    for retirement in transaction.retirements:
        previous = resolutions.get(retirement.resolution_id)
        if previous is None or previous.target != retirement.target:
            raise ValueError("retirement requires an exact standing resolution")
        if not historical and retirement.resolution_id in withdrawn:
            raise ValueError("a withdrawn resolution cannot have evidence retired")
        original = next(
            entry.approval.commit for entry in entries if previous in entry.transaction.resolutions
        )
        for target in retirement.targets:
            source_path(repository, target)
            existed = any(
                committed_blob_identity(repository, revision, target) is not None
                for revision in (record.contract.approved_base, original)
            )
            if not existed or committed_blob_identity(repository, commit, target) is not None:
                raise ValueError(
                    "retirement requires committed evidence deletion since the approved base"
                )


def _replace(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".events-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def append_transaction(
    repository: Path, transaction: DevelopmentTransaction, *, expected_history: str
) -> DevelopmentSnapshot:
    """Validate the whole transaction before the single atomic source append."""
    repository = repository.resolve()
    validate_transaction(transaction)
    authority_roots(repository)  # New writes require the current active manifest.
    with _writer(repository) as root:
        branch = git_output(repository, "symbolic-ref", "--quiet", "--short", "HEAD")
        workspace = read_record(root, branch)
        if workspace.kind != "member":
            raise ValueError("source history can only be written by a member workspace")
        current = read_sources(repository)
        existing = [item for item in current.entries if item.transaction.id == transaction.id]
        if existing:
            if existing[0].transaction != transaction:
                raise ValueError("development transaction identity has different content")
            return judge_sources(repository, current)
        if expected_history != current.history_digest:
            raise ValueError("development history changed; review the current working set again")
        commit = git_output(repository, "rev-parse", "HEAD")
        require_committed_bindings(repository, commit)
        record, proof = approved_authority(repository, transaction.change_id, commit)
        if record.contract.approved_base != workspace.base:
            raise ValueError("approved change base differs from the registered workspace base")
        working = parse_change_record(source_path(repository, proof.path).read_text())
        if (
            working.id != record.id
            or working.contract != record.contract
            or working.approval != record.approval
            or working.source != record.source
            or working.status != record.status
        ):
            raise ValueError("uncommitted authority changes cannot authorize source history")
        _validate_payload(repository, transaction, record, commit)
        _resolution_targets(repository, transaction, current.entries, record, commit)
        target = source_path(repository, str(PurePosixPath(proof.path).with_name("events.jsonl")))
        ignored = run_git(
            repository,
            "check-ignore",
            "--no-index",
            "--quiet",
            "--",
            str(target.relative_to(repository)),
        ).returncode
        if ignored == 0:
            raise ValueError("source journal must not be ignored")
        if ignored != 1:
            raise ValueError("source journal tracking policy is unavailable")
        before = target.read_bytes() if target.exists() else b""
        entry = DevelopmentEntry(
            sequence=len(before.splitlines()) + 1,
            previous_digest=_digest(before),
            approval=proof,
            transaction=transaction,
        )
        candidate = _SourceHistory(
            current.head,
            current.history_digest,
            (*current.entries, entry),
            {**current.authorities, (transaction.change_id, proof.commit): (record, proof)},
        )
        judge_sources(repository, candidate)
        claim_change(root, transaction.change_id, branch)
        if git_output(repository, "rev-parse", "HEAD") != commit:
            raise ValueError("source commit changed during journal validation")
        if read_sources(repository).history_digest != current.history_digest:
            raise ValueError("development history changed during transaction validation")
        # Copy-on-write preserves the exact old prefix and exposes no partial
        # transaction. Current decisions are derived, so there is no second
        # independently writable projection to reconcile after a crash.
        _replace(target, before + _json(contract_mapping(entry)) + b"\n")
        return snapshot(repository)


def historical_authorities(repository: Path, commit: str) -> list[dict[str, object]]:
    """Discover declared standing from committed sources, without interpreting prose."""
    _, root = authority_roots(repository, commit=commit)
    decisions = []
    for name in git_output(
        repository, "ls-tree", "-r", "--name-only", "-z", commit, "--", root
    ).split("\0"):
        if not name.endswith(".md"):
            continue
        blob = committed_blob(repository, commit, name)
        if blob is not None:
            decision = parse_decision(blob[1], name)
            if decision.status == DecisionStatus.ACCEPTED:
                decisions.append((decision, blob))
    by_name = {decision.name: decision for decision, _ in decisions}
    return [
        {
            "path": decision.path,
            "blob": blob[0],
            "status": decision.status.value,
            "superseded_by": list(decision.superseded_by),
            "standing": "superseded"
            if complete_decision_replacements(decision, by_name)
            else "retained",
            "title": next(
                (line.removeprefix("# ") for line in blob[1].splitlines() if line.startswith("# ")),
                decision.name,
            ),
        }
        for decision, blob in decisions
    ]
