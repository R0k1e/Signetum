# Generated from signetum.deviations; edit the engine source and regenerate.
"""Read-only historical deviation decoding and delivery review projections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, TypedDict

from .change_models import Identifier
from .change_record import load_repository_record, review_view
from .contract_values import FrozenContract
from .git import GitError, git_output, run_git
from .serialization import (
    Constraints,
    ValueDecodeError,
    contract_mapping,
    dataclass_from_mapping,
    load_json,
    validate_value,
)


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
                    "historical": True,
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
    try:
        return review_view(load_repository_record(repository, f"{root}/{change_id}/change.toml"))
    except (OSError, ValueError) as error:
        raise DeviationError(f"current approval is unavailable: {error}") from error


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
    if resolution.resolution == ResolutionKind.DEFERRED:
        raise DeviationError("historical deferral requires explicit current-change reconciliation")
    for raw_target in resolution.targets:
        target = PurePosixPath(raw_target)
        if target.is_absolute() or ".." in target.parts or str(target) in {"", "."}:
            raise DeviationError(f"historical target is not repository-relative: {raw_target}")
    # These are preserved historical claims, not new grants under current policy.
    # Retired evidence remains named even when an approved change removed the file.
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
