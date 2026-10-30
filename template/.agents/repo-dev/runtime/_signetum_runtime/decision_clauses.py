# Generated from signetum.decision_clauses; edit the engine source and regenerate.
"""Apply already-authorized clause edits without whole-document override.

The repository boundary owns approval and append-only persistence. This pure
owner validates exact expected versions and projects the accepted event batch.
"""

from dataclasses import dataclass, replace
from typing import Annotated, Literal

from .change_models import ClauseId, Identifier
from .contract_values import FrozenContract
from .serialization import Constraints

Text = Annotated[str, Constraints(min_length=1)]
Version = Annotated[int, Constraints(minimum=1)]


class DecisionEditError(ValueError):
    """An edit conflicts with the current set or strands another clause."""


@dataclass(frozen=True, kw_only=True)
class ClauseRevision(FrozenContract):
    id: ClauseId
    version: Version
    topic: Identifier
    scope: Annotated[tuple[Text, ...], Constraints(min_length=1)]
    statement: Text
    rationale: Text
    status: Literal["active", "withdrawn"] = "active"
    requires: tuple[ClauseId, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EffectiveClause(FrozenContract):
    revision: ClauseRevision
    source_event: Identifier


@dataclass(frozen=True, kw_only=True)
class ExpectedClause(FrozenContract):
    id: ClauseId
    version: Annotated[int, Constraints(minimum=0)]


@dataclass(frozen=True, kw_only=True)
class DecisionEdit(FrozenContract):
    id: Identifier
    change_id: Identifier
    action: Literal["add", "amend", "withdraw", "split", "merge"]
    expected: Annotated[tuple[ExpectedClause, ...], Constraints(min_length=1)]
    updates: Annotated[tuple[ClauseRevision, ...], Constraints(min_length=1)]
    reason: Text
    authority: Text


def _unique(values: tuple[str, ...], label: str) -> None:
    if len(set(values)) != len(values):
        raise DecisionEditError(f"duplicate {label}")


def _edit(state: dict[str, EffectiveClause], event: DecisionEdit) -> None:
    _unique(tuple(item.id for item in event.expected), "expected clause")
    _unique(tuple(item.id for item in event.updates), "updated clause")
    expected = {item.id: item.version for item in event.expected}
    updates = {item.id: item for item in event.updates}
    if set(expected) != set(updates):
        raise DecisionEditError("every updated clause requires its exact prior version")
    old = {identity for identity, version in expected.items() if version}
    new = set(expected) - old
    if event.action == "add":
        valid = not old
    elif event.action in {"amend", "withdraw"}:
        valid = bool(old) and not new
    elif event.action == "split":
        valid = len(old) == 1 and len(new) >= 2
    else:
        valid = len(old) >= 2 and len(new) == 1
    if not valid:
        raise DecisionEditError(f"invalid affected clause set for {event.action}")
    withdrawing = event.action in {"withdraw", "split", "merge"}
    for identity, version in expected.items():
        current = state.get(identity)
        candidate = updates[identity]
        observed = current.revision.version if current else 0
        if observed != version:
            raise DecisionEditError(
                f"stale decision clause {identity}: expected {version}, observed {observed}"
            )
        if candidate.version != version + 1:
            raise DecisionEditError(f"decision clause {identity} must advance exactly one version")
        if current is None:
            if candidate.status != "active":
                raise DecisionEditError("new clauses must be active")
        elif withdrawing:
            previous = current.revision
            if previous.status != "active" or candidate != replace(
                previous, version=version + 1, status="withdrawn"
            ):
                raise DecisionEditError("withdrawal preserves the original clause content")
        else:
            if candidate.status != "active":
                raise DecisionEditError("amendments must leave the clause active")
            if replace(candidate, version=version) == current.revision:
                raise DecisionEditError("an amendment must change the clause")
        _unique(candidate.requires, "required clause")
        state[identity] = EffectiveClause(revision=candidate, source_event=event.id)


def _relations(state: dict[str, EffectiveClause]) -> None:
    active = {key: item.revision for key, item in state.items() if item.revision.status == "active"}
    visited: set[str] = set()
    pending: set[str] = set()

    def visit(identity: str) -> None:
        if identity in pending:
            raise DecisionEditError(f"cyclic decision requirement at {identity}")
        if identity in visited:
            return
        if identity not in active:
            raise DecisionEditError(f"decision requirement is absent or withdrawn: {identity}")
        pending.add(identity)
        for dependency in active[identity].requires:
            visit(dependency)
        pending.remove(identity)
        visited.add(identity)

    for identity in active:
        visit(identity)


def apply_decision_edits(
    current: tuple[EffectiveClause, ...], events: tuple[DecisionEdit, ...]
) -> tuple[EffectiveClause, ...]:
    """Project one transaction; errors leave the caller's immutable state intact."""
    _unique(tuple(item.revision.id for item in current), "current clause")
    _unique(tuple(item.id for item in events), "decision event")
    state = {item.revision.id: item for item in current}
    _relations(state)
    for event in events:
        _edit(state, event)
    _relations(state)
    return tuple(state[key] for key in sorted(state))
