# Generated from signetum.deviations; edit the engine source and regenerate.
"""Signetum-owned execution deviations and human review projections."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, TypedDict

from .change_authority import validate_specification_authority
from .change_models import DecisionStatus, Identifier
from .change_paths import changes_root
from .change_record import load_repository_record, review_view
from .contract_values import FrozenContract
from .git import GitError, git_output, run_git
from .manifest import ManifestError, load_manifest
from .serialization import (
    Constraints,
    ValueDecodeError,
    contract_mapping,
    dataclass_from_mapping,
    load_json,
    validate_value,
)
from .traceability_loading import load_decision
from .workspaces import WorkspaceError, claim_change


class DeviationError(ValueError):
    """The requested deviation operation violates the ledger contract."""


class DeviationClass(StrEnum):
    IMPLEMENTATION_CLARIFICATION = "implementation_clarification"
    SAFE_SUPPORTING_CHANGE = "safe_supporting_change"
    DECISION_REQUIRED = "decision_required"


class ResolutionKind(StrEnum):
    RESOLVED_IN_SPECIFICATION = "resolved_in_specification"
    RESOLVED_IN_DECISION = "resolved_in_decision"
    RESOLVED_IN_ARCHITECTURE = "resolved_in_architecture"
    RESOLVED_IN_TESTS = "resolved_in_tests"
    NO_AUTHORITY_CHANGE = "no_authority_change"
    DEFERRED = "deferred"
    REJECTED = "rejected"


@dataclass(frozen=True, kw_only=True)
class Discovered(FrozenContract):
    event: Literal["discovered"] = "discovered"
    id: Identifier
    change_id: Identifier
    member: Annotated[str, Constraints(min_length=1)]
    at: datetime
    summary: Annotated[str, Constraints(min_length=1)]
    classification: DeviationClass
    original_commitment: Annotated[str, Constraints(min_length=1)]
    action: Annotated[str, Constraints(min_length=1)]
    impact: Annotated[str, Constraints(min_length=1)]
    source_commit: Annotated[str | None, Constraints(pattern="^[0-9a-f]{40}(?:[0-9a-f]{24})?$")] = (
        None
    )


@dataclass(frozen=True, kw_only=True)
class Resolved(FrozenContract):
    event: Literal["resolved"] = "resolved"
    id: Identifier
    change_id: Identifier
    member: Annotated[str, Constraints(min_length=1)]
    at: datetime
    resolution: ResolutionKind
    targets: tuple[str, ...] = ()
    reason: Annotated[str, Constraints(min_length=1)]
    implemented: bool


DeviationEvent = Discovered | Resolved


def event_json(value: DeviationEvent | DeviationState) -> str:
    return json.dumps(contract_mapping(value), ensure_ascii=False, separators=(",", ":"))


def parse_event(source: bytes) -> DeviationEvent:
    document = load_json(source.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueDecodeError("deviation event must be an object")
    if document.get("event") == "discovered":
        return dataclass_from_mapping(Discovered, document, use_defaults=True)
    if document.get("event") == "resolved":
        return dataclass_from_mapping(Resolved, document, use_defaults=True)
    raise ValueDecodeError("unknown or absent deviation event discriminator")


@dataclass(frozen=True, kw_only=True)
class DeviationState(FrozenContract):
    discovered: Discovered
    resolution: Resolved | None = None


def git_common_dir(repository: Path) -> Path:
    """Resolve the one common Git directory shared by linked worktrees."""
    try:
        output = git_output(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
    except GitError as error:
        raise DeviationError(str(error)) from error
    common = Path(output)
    if not common.is_absolute():
        raise DeviationError("Git returned a non-absolute common directory")
    return common.resolve()


def ledger_path(repository: Path, change_id: str) -> Path:
    """Return the deterministic per-change ledger path."""
    _validate_identity(change_id)
    return git_common_dir(repository) / "signetum" / "changes" / change_id / "deviations.jsonl"


def append_event(repository: Path, event: DeviationEvent) -> Path:
    """Validate and append exactly one complete event with O_APPEND semantics."""
    if isinstance(event, Discovered):
        require_change_workspace(repository, event.change_id, event.member)
        source = git_output(repository, "rev-parse", "HEAD")
        if event.source_commit is not None and event.source_commit != source:
            raise DeviationError("discovery source differs from the observed member commit")
        event = replace(event, **{"source_commit": source})
        try:
            claim_change(git_common_dir(repository) / "signetum", event.change_id, event.member)
        except WorkspaceError as error:
            raise DeviationError(str(error)) from error
    else:
        registered = git_output(repository, "worktree", "list", "--porcelain").splitlines()
        if f"branch refs/heads/{event.member}" in registered:
            require_change_workspace(repository, event.change_id, event.member)
    target = ledger_path(repository, event.change_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = event_json(event).encode("utf-8") + b"\n"
    if len(encoded) > 65_536:
        raise DeviationError("deviation event exceeds the atomic record bound")
    descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        written = os.write(descriptor, encoded)
        if written != len(encoded):
            raise DeviationError("deviation event append was incomplete")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return target


def require_change_workspace(repository: Path, change_id: str, member: str) -> None:
    _validate_identity(change_id)
    try:
        branch = git_output(repository, "symbolic-ref", "--quiet", "--short", "HEAD")
    except GitError as error:
        raise DeviationError(str(error)) from error
    if branch != member:
        raise DeviationError(f"member {member} is not the branch checked out here: {branch}")
    manifest_path = repository / "signetum.toml"
    root = changes_root(load_manifest(manifest_path)) if manifest_path.exists() else "changes"
    if not (repository / root / change_id).is_dir():
        raise DeviationError(f"change package {root}/{change_id} is absent from member {member}")


def changes_naming_member(
    repository: Path, member: str, *, tips: Sequence[str] | None = None
) -> tuple[str, ...]:
    root = git_common_dir(repository) / "signetum" / "changes"
    named: list[str] = []
    for ledger in sorted(root.rglob("deviations.jsonl")):
        if json.dumps(member) not in ledger.read_text(encoding="utf-8"):
            continue
        change_id = ledger.parent.relative_to(root).as_posix()
        if any(
            state.discovered.member == member
            and _visible_state(repository, state, {member: tips} if tips is not None else None)
            for state in read_states(repository, change_id)
        ):
            named.append(change_id)
    return tuple(named)


def read_states(repository: Path, change_id: str) -> tuple[DeviationState, ...]:
    """Reduce the strict append-only ledger into one current state per deviation."""
    target = ledger_path(repository, change_id)
    if not target.exists():
        return ()
    discovered: dict[str, Discovered] = {}
    resolved: dict[str, Resolved] = {}
    try:
        lines = target.read_bytes().splitlines()
    except OSError as error:
        raise DeviationError(f"deviation ledger is unreadable: {error}") from error
    for number, line in enumerate(lines, start=1):
        try:
            event = parse_event(line)
        except ValueError as error:
            raise DeviationError(f"invalid deviation event at line {number}: {error}") from error
        if event.change_id != change_id:
            raise DeviationError(f"deviation event at line {number} belongs to another change")
        if isinstance(event, Discovered):
            if event.id in discovered:
                raise DeviationError(f"duplicate deviation discovery: {event.id}")
            if event.id in resolved:
                raise DeviationError(f"deviation resolved before discovery: {event.id}")
            discovered[event.id] = event
        else:
            if event.id not in discovered:
                raise DeviationError(f"deviation resolved before discovery: {event.id}")
            if event.id in resolved:
                raise DeviationError(f"duplicate deviation resolution: {event.id}")
            if event.member != discovered[event.id].member:
                raise DeviationError(f"deviation member changed during resolution: {event.id}")
            resolved[event.id] = event
    return tuple(
        DeviationState(discovered=item, resolution=resolved.get(item.id))
        for item in sorted(discovered.values(), key=lambda value: value.id)
    )


def _visible_state(
    repository: Path, state: DeviationState, member_tips: Mapping[str, Sequence[str]] | None
) -> bool:
    event = state.discovered
    if member_tips is None or event.member not in member_tips or event.source_commit is None:
        return True
    for tip in member_tips[event.member]:
        result = run_git(repository, "merge-base", "--is-ancestor", event.source_commit, tip)
        if result.returncode == 0:
            return True
        if result.returncode != 1:
            raise DeviationError(f"discovery source cannot be verified: {event.source_commit}")
    return False


class ReviewSnapshot(TypedDict):
    changes: list[str]
    members: list[str]
    ledgers: dict[str, str]


def review_snapshot(
    repository: Path,
    change_ids: tuple[str, ...],
    members: tuple[str, ...],
    *,
    member_tips: Mapping[str, Sequence[str]] | None = None,
) -> ReviewSnapshot:
    """Bind retained execution records, including newly named change packages."""
    selected = set(change_ids)
    for member in members:
        selected.update(
            changes_naming_member(
                repository,
                member,
                tips=member_tips.get(member) if member_tips is not None else None,
            )
        )
    ledgers: dict[str, str] = {}
    for change_id in sorted(selected):
        states = tuple(
            state
            for state in read_states(repository, change_id)
            if _visible_state(repository, state, member_tips)
        )
        content = b"\n".join(event_json(state).encode("utf-8") for state in states)
        ledgers[change_id] = hashlib.sha256(content).hexdigest()
    return {"changes": sorted(selected), "members": sorted(set(members)), "ledgers": ledgers}


def reconciliation_summary(
    repository: Path,
    change_ids: tuple[str, ...],
    *,
    target_moves: Mapping[str, str] | None = None,
    member_tips: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, object]:
    """Validate terminal resolutions and return delivery-review source data."""
    changes: list[dict[str, object]] = []
    pending: list[str] = []
    deviation_count = 0
    extra_work: list[str] = []
    unfinished_work: list[str] = []
    authority_updates: set[str] = set()
    for change_id in sorted(set(change_ids)):
        states = tuple(
            state
            for state in read_states(repository, change_id)
            if _visible_state(repository, state, member_tips)
        )
        rows: list[dict[str, object]] = []
        for state in states:
            recorded_targets = state.resolution.targets if state.resolution else ()
            if state.resolution and target_moves:
                state = replace(
                    state,
                    **{
                        "resolution": replace(
                            state.resolution,
                            **{
                                "targets": tuple(
                                    target_moves.get(path, path) for path in recorded_targets
                                )
                            },
                        )
                    },
                )
            deviation_count += 1
            if state.resolution is None:
                pending.append(f"{change_id}/{state.discovered.id}")
            else:
                _validate_resolution(repository, state)
                authority_updates.update(state.resolution.targets)
                if state.resolution.resolution == ResolutionKind.DEFERRED:
                    unfinished_work.append(f"{change_id}/{state.discovered.id}")
            if state.discovered.classification == DeviationClass.SAFE_SUPPORTING_CHANGE:
                extra_work.append(f"{change_id}/{state.discovered.id}")
            rows.append(
                {
                    "id": state.discovered.id,
                    "summary": state.discovered.summary,
                    "classification": state.discovered.classification.value,
                    "member": state.discovered.member,
                    "source_commit": state.discovered.source_commit,
                    "resolution": (
                        state.resolution.resolution.value
                        if state.resolution is not None
                        else "pending"
                    ),
                    "targets": list(state.resolution.targets) if state.resolution else [],
                    "recorded_targets": list(recorded_targets),
                    "reason": state.resolution.reason if state.resolution else "",
                }
            )
        changes.append({"change_id": change_id, "deviations": rows})
    if pending:
        raise DeviationError(f"unresolved deviations: {', '.join(pending)}")
    return {
        "changes": changes,
        "deviation_count": deviation_count,
        "extra_work": extra_work,
        "unfinished_work": unfinished_work,
        "authority_updates": sorted(authority_updates),
    }


def approval_view(repository: Path, change_id: str, *, root: str = "changes") -> dict[str, object]:
    """Project the tracked Review and Specification into a concise approval payload."""
    _validate_identity(change_id)
    change = repository.resolve() / root / change_id
    consolidated = change / "change.toml"
    if consolidated.exists() or consolidated.is_symlink():
        try:
            return review_view(
                load_repository_record(repository, f"{root}/{change_id}/change.toml")
            )
        except (OSError, ValueError) as error:
            raise DeviationError(f"consolidated approval is unavailable: {error}") from error
    try:
        review = tomllib.loads((change / "review.toml").read_text(encoding="utf-8"))["review"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise DeviationError(f"approved Review is unavailable: {error}") from error
    clauses = review.get("clauses")
    if not isinstance(clauses, list):
        raise DeviationError("Review clauses are unavailable")
    commitments = [
        item.get("statement")
        for item in clauses
        if isinstance(item, dict) and item.get("disposition") == "covered"
    ]
    non_goals = [
        {"statement": item.get("statement"), "reason": item.get("reason")}
        for item in clauses
        if isinstance(item, dict) and item.get("disposition") == "out_of_scope"
    ]
    deferred = [
        item.get("statement")
        for item in clauses
        if isinstance(item, dict) and item.get("disposition") == "deferred"
    ]
    if not commitments or not all(isinstance(item, str) and item for item in commitments):
        raise DeviationError("Review commitments are invalid")
    specs = sorted((change / "specs").glob("*.toml"))
    evidence: list[str] = []
    for path in specs:
        try:
            specification = tomllib.loads(path.read_text(encoding="utf-8"))["specification"]
        except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
            raise DeviationError(f"Specification is unavailable: {error}") from error
        if (
            specification.get("status") != "approved"
            or specification.get("implementation_authorized") is not True
        ):
            raise DeviationError(f"Specification is not implementation-authorized: {path}")
        raw_acceptance = specification.get("acceptance", ())
        if isinstance(raw_acceptance, list):
            evidence.extend(str(item) for item in raw_acceptance)
    return {
        "schema_version": 1,
        "status": "approval",
        "change_id": change_id,
        "outcomes": commitments,
        "non_goals": non_goals,
        "deferred": deferred,
        "acceptance": evidence,
        "autonomy": {
            "continue": ["implementation_clarification", "safe_supporting_change"],
            "freeze_affected_work": ["decision_required"],
        },
    }


def _validate_resolution(repository: Path, state: DeviationState) -> None:
    resolution = state.resolution
    if resolution is None:
        raise DeviationError(f"unresolved deviation: {state.discovered.id}")
    target_required = resolution.resolution in {
        ResolutionKind.RESOLVED_IN_SPECIFICATION,
        ResolutionKind.RESOLVED_IN_DECISION,
        ResolutionKind.RESOLVED_IN_ARCHITECTURE,
        ResolutionKind.RESOLVED_IN_TESTS,
        ResolutionKind.DEFERRED,
    }
    if target_required and not resolution.targets:
        raise DeviationError(f"resolution requires an authority target: {resolution.id}")
    manifest_path = repository / "signetum.toml"
    manifest = load_manifest(manifest_path) if manifest_path.is_file() else None
    root = changes_root(manifest) if manifest is not None else "changes"
    decisions = manifest.repository.decisions if manifest is not None else "docs/decisions"
    for raw_target in resolution.targets:
        target = PurePosixPath(raw_target)
        if target.is_absolute() or ".." in target.parts or str(target) in {"", "."}:
            raise DeviationError(f"resolution target is not repository-relative: {raw_target}")
        path = repository.resolve() / target
        if not path.resolve().is_relative_to(repository.resolve()):
            raise DeviationError(f"resolution target escapes the repository: {raw_target}")
        if not path.is_file():
            raise DeviationError(f"resolution target is absent or not a file: {raw_target}")
        if resolution.resolution in {
            ResolutionKind.DEFERRED,
            ResolutionKind.RESOLVED_IN_SPECIFICATION,
        }:
            try:
                validate_specification_authority(
                    repository,
                    target,
                    root=root,
                    decisions=decisions,
                    approved=resolution.resolution == ResolutionKind.RESOLVED_IN_SPECIFICATION,
                )
            except (OSError, ValueError) as error:
                raise DeviationError(f"invalid resolution specification: {error}") from error
        if resolution.resolution == ResolutionKind.RESOLVED_IN_DECISION:
            if not target.is_relative_to(PurePosixPath(decisions)):
                raise DeviationError(
                    f"decision resolution target is outside decisions: {raw_target}"
                )
            if load_decision(path, raw_target).status != DecisionStatus.ACCEPTED:
                raise DeviationError(f"decision resolution target is not accepted: {raw_target}")
    if (
        state.discovered.classification == DeviationClass.DECISION_REQUIRED
        and resolution.implemented
    ):
        approved = resolution.resolution in {
            ResolutionKind.RESOLVED_IN_SPECIFICATION,
            ResolutionKind.RESOLVED_IN_DECISION,
        }
        if not approved:
            raise DeviationError(
                f"decision-required deviation was implemented without authority: {resolution.id}"
            )


def _validate_identity(value: str) -> None:
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise DeviationError(f"invalid change identity: {value}")
    try:
        validate_value(value, Identifier)
    except ValueError as error:
        raise DeviationError(f"invalid change identity: {value}") from error


@contextmanager
def _ledger_write(repository: Path, change_id: str) -> Iterator[None]:
    """Serialize each public check-and-append transition, without waiting."""
    parent = ledger_path(repository, change_id).parent
    parent.mkdir(parents=True, exist_ok=True)
    with (parent / "ledger.lock").open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DeviationError("change ledger has an active update; retry") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    commands = parser.add_subparsers(dest="command", required=True)
    approval = commands.add_parser("approval")
    approval.add_argument("--change", required=True)
    record = commands.add_parser("record")
    record.add_argument("--change", required=True)
    record.add_argument("--id", required=True)
    record.add_argument("--member", required=True)
    record.add_argument(
        "--class", dest="classification", choices=tuple(DeviationClass), required=True
    )
    record.add_argument("--summary", required=True)
    record.add_argument("--commitment", required=True)
    record.add_argument("--action", required=True)
    record.add_argument("--impact", required=True)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--change", required=True)
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--member", required=True)
    resolve.add_argument("--resolution", choices=tuple(ResolutionKind), required=True)
    resolve.add_argument("--target", action="append", default=[])
    resolve.add_argument("--reason", required=True)
    resolve.add_argument("--implemented", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("--change", required=True, action="append")
    return parser


def main(arguments: list[str] | None = None) -> int:
    parsed = _parser().parse_args(arguments)
    repository = parsed.repository.resolve()
    try:
        with (
            _ledger_write(repository, parsed.change)
            if parsed.command in {"record", "resolve"}
            else nullcontext()
        ):
            if parsed.command == "approval":
                result = approval_view(repository, parsed.change)
            elif parsed.command == "record":
                event = Discovered(
                    id=parsed.id,
                    change_id=parsed.change,
                    member=parsed.member,
                    at=datetime.now(UTC),
                    summary=parsed.summary,
                    classification=DeviationClass(parsed.classification),
                    original_commitment=parsed.commitment,
                    action=parsed.action,
                    impact=parsed.impact,
                )
                if any(
                    state.discovered.id == event.id
                    for state in read_states(repository, event.change_id)
                ):
                    raise DeviationError(f"duplicate deviation discovery: {event.id}")
                path = append_event(repository, event)
                result = {
                    "schema_version": 1,
                    "status": "recorded",
                    "id": event.id,
                    "ledger": str(path),
                }
            elif parsed.command == "resolve":
                event = Resolved(
                    id=parsed.id,
                    change_id=parsed.change,
                    member=parsed.member,
                    at=datetime.now(UTC),
                    resolution=ResolutionKind(parsed.resolution),
                    targets=tuple(parsed.target),
                    reason=parsed.reason,
                    implemented=parsed.implemented,
                )
                states = {
                    state.discovered.id: state for state in read_states(repository, parsed.change)
                }
                if parsed.id not in states:
                    raise DeviationError(f"deviation is absent: {parsed.id}")
                state = states[parsed.id]
                if state.resolution is not None:
                    raise DeviationError(f"duplicate deviation resolution: {event.id}")
                if event.member != state.discovered.member:
                    raise DeviationError(f"deviation member changed during resolution: {event.id}")
                _validate_resolution(repository, replace(state, **{"resolution": event}))
                path = append_event(repository, event)
                result = {
                    "schema_version": 1,
                    "status": "resolved",
                    "id": event.id,
                    "ledger": str(path),
                }
            else:
                result = {
                    "schema_version": 1,
                    "status": "reconciled",
                    **reconciliation_summary(repository, tuple(parsed.change)),
                }
    except (DeviationError, OSError, ManifestError, ValueError) as error:
        print(
            json.dumps(
                {"schema_version": 1, "status": "refused", "reason": str(error)}, sort_keys=True
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
