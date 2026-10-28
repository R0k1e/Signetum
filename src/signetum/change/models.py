"""Versioned, immutable models for requirement closure."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated

from signetum.contract_values import FrozenContract
from signetum.serialization import Constraints, JsonValue

Identifier = Annotated[str, Constraints(min_length=1, pattern="^[A-Za-z0-9][A-Za-z0-9._/-]*$")]
ClauseId = Annotated[str, Constraints(min_length=1, pattern="^[A-Za-z0-9][A-Za-z0-9._-]*$")]


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    APPROVED = "approved"
    COMPLETE = "complete"
    COMPLETED = "completed"
    CLOSED = "closed"


class SpecificationStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DRAFT = "draft"


@dataclass(frozen=True, kw_only=True)
class Decision(FrozenContract):
    """One decision as its own file declares itself."""

    path: str
    status: DecisionStatus
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    partially_supersedes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not set(self.partially_supersedes) <= set(self.supersedes):
            raise ValueError("partial supersessions must also be declared under Supersedes")

    @property
    def name(self) -> str:
        """Return the file name other decisions cite this one by."""
        return self.path.rsplit("/", 1)[-1]


@dataclass(frozen=True, kw_only=True)
class ReviewSource(FrozenContract):
    kind: Identifier
    summary: Annotated[str, Constraints(min_length=1)]


class ClauseDisposition(StrEnum):
    COVERED = "covered"
    DEFERRED = "deferred"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True, kw_only=True)
class Clause(FrozenContract):
    id: ClauseId
    statement: Annotated[str, Constraints(min_length=1)]
    disposition: ClauseDisposition = ClauseDisposition.COVERED
    specification: Identifier | None = None
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class HumanAuthority(FrozenContract):
    actor: Annotated[str, Constraints(min_length=1)]
    recorded_at: date
    reason: Annotated[str, Constraints(min_length=1)]


@dataclass(frozen=True, kw_only=True)
class ClauseExclusion(FrozenContract):
    clause: ClauseId
    authority: HumanAuthority


@dataclass(frozen=True, kw_only=True)
class Acceptance(FrozenContract):
    delivery_commit: Annotated[str, Constraints(min_length=1)]
    accepted_clauses: tuple[ClauseId, ...] = ()
    rejected_clauses: tuple[ClauseId, ...] = ()
    authority: HumanAuthority

    def __post_init__(self) -> None:
        super().__post_init__()
        if set(self.accepted_clauses) & set(self.rejected_clauses):
            raise ValueError("accepted and rejected clauses must be disjoint")


@dataclass(frozen=True, kw_only=True)
class Reopen(FrozenContract):
    clause: ClauseId
    delivery_commit: Annotated[str, Constraints(min_length=1)]
    authority: HumanAuthority


@dataclass(frozen=True, kw_only=True)
class Review(FrozenContract):
    schema_version: Annotated[int, Constraints(minimum=1)]
    id: Identifier
    status: ReviewStatus
    recorded_at: date | None = None
    source: ReviewSource
    clauses: Annotated[tuple[Clause, ...], Constraints(min_length=1)]
    acceptance: "ReviewAcceptance" = field(default_factory=lambda: ReviewAcceptance())

    def __post_init__(self) -> None:
        super().__post_init__()
        identifiers = [clause.id for clause in self.clauses]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("review clause identifiers must be unique")


class AcceptanceResult(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REOPENED = "reopened"


@dataclass(frozen=True, kw_only=True)
class ReviewAcceptance(FrozenContract):
    result: AcceptanceResult = AcceptanceResult.PENDING
    delivery_commit: str | None = None
    accepted_clauses: tuple[ClauseId, ...] = ()
    rejected_clauses: tuple[ClauseId, ...] = ()
    linked_change: Identifier | None = None


@dataclass(frozen=True, kw_only=True)
class ReviewReference(FrozenContract):
    id: Identifier
    clauses: Annotated[tuple[ClauseId, ...], Constraints(min_length=1)]


@dataclass(frozen=True, kw_only=True)
class ClauseOwnership(FrozenContract):
    clause: ClauseId


@dataclass(frozen=True, kw_only=True)
class Deferral(FrozenContract):
    clause: ClauseId
    target_specification: Identifier
    authority: HumanAuthority


@dataclass(frozen=True, kw_only=True)
class Supersession(FrozenContract):
    specification: Identifier
    authority: HumanAuthority


@dataclass(frozen=True, kw_only=True)
class Specification(FrozenContract):
    schema_version: Annotated[int, Constraints(minimum=1)]
    id: Identifier
    version: Annotated[int, Constraints(minimum=1)]
    status: SpecificationStatus
    implementation_authorized: bool
    review: ReviewReference
    decisions: tuple[str, ...] = ()
    plan: str
    ownership: tuple[ClauseOwnership, ...] = ()
    deferrals: tuple[Deferral, ...] = ()
    supersedes: tuple[Supersession, ...] = ()
    intent: tuple[str, ...] = ()
    extensions: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.ownership and tuple(item.clause for item in self.ownership) != self.review.clauses:
            raise ValueError("ownership must exactly match the review clause claims")

    @property
    def owned_clauses(self) -> tuple[ClauseId, ...]:
        if self.ownership:
            return tuple(item.clause for item in self.ownership)
        return self.review.clauses


@dataclass(frozen=True, kw_only=True)
class PlanObligation(FrozenContract):
    id: Identifier
    clauses: Annotated[tuple[ClauseId, ...], Constraints(min_length=1)]
    outcome: Annotated[str, Constraints(min_length=1)]
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Plan(FrozenContract):
    schema_version: Annotated[int, Constraints(minimum=1)] = 1
    id: Identifier
    status: PlanStatus
    specification: str
    approved_base: Annotated[str, Constraints(min_length=1)]
    obligations: Annotated[tuple[PlanObligation, ...], Constraints(min_length=1)]

    def __post_init__(self) -> None:
        super().__post_init__()
        identifiers = [obligation.id for obligation in self.obligations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("plan obligation identifiers must be unique")


def require_relative_path(value: str) -> PurePosixPath:
    """Return a normalized repository-relative reference or reject it."""
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
        raise ValueError(f"reference is not a repository-relative path: {value}")
    return path
