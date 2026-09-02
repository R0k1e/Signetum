"""Versioned, immutable models for requirement closure."""

from datetime import date
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")]
ClauseId = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]


class FrozenModel(BaseModel):
    """The common strict and immutable boundary contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


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


class Decision(FrozenModel):
    """One decision as its own file declares itself."""

    path: str
    status: DecisionStatus
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        """Return the file name other decisions cite this one by."""

        return self.path.rsplit("/", 1)[-1]


class ReviewSource(FrozenModel):
    kind: Identifier
    summary: str = Field(min_length=1)


class ClauseDisposition(StrEnum):
    COVERED = "covered"
    DEFERRED = "deferred"
    OUT_OF_SCOPE = "out_of_scope"


class Clause(FrozenModel):
    id: ClauseId
    statement: str = Field(min_length=1)
    disposition: ClauseDisposition = ClauseDisposition.COVERED
    specification: Identifier | None = None
    reason: str | None = None


class HumanAuthority(FrozenModel):
    actor: str = Field(min_length=1)
    recorded_at: date
    reason: str = Field(min_length=1)


class ClauseExclusion(FrozenModel):
    clause: ClauseId
    authority: HumanAuthority


class Acceptance(FrozenModel):
    delivery_commit: str = Field(min_length=1)
    accepted_clauses: tuple[ClauseId, ...] = ()
    rejected_clauses: tuple[ClauseId, ...] = ()
    authority: HumanAuthority

    @model_validator(mode="after")
    def disjoint_results(self) -> "Acceptance":
        if set(self.accepted_clauses) & set(self.rejected_clauses):
            raise ValueError("accepted and rejected clauses must be disjoint")
        return self


class Reopen(FrozenModel):
    clause: ClauseId
    delivery_commit: str = Field(min_length=1)
    authority: HumanAuthority


class Review(FrozenModel):
    schema_version: int = Field(ge=1)
    id: Identifier
    status: ReviewStatus
    recorded_at: date | None = None
    source: ReviewSource
    clauses: tuple[Clause, ...] = Field(min_length=1)
    acceptance: "ReviewAcceptance" = Field(default_factory=lambda: ReviewAcceptance())

    @model_validator(mode="after")
    def unique_clauses(self) -> "Review":
        identifiers = [clause.id for clause in self.clauses]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("review clause identifiers must be unique")
        return self


class AcceptanceResult(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REOPENED = "reopened"


class ReviewAcceptance(FrozenModel):
    result: AcceptanceResult = AcceptanceResult.PENDING
    delivery_commit: str | None = None
    accepted_clauses: tuple[ClauseId, ...] = ()
    rejected_clauses: tuple[ClauseId, ...] = ()
    linked_change: Identifier | None = None


class ReviewReference(FrozenModel):
    id: Identifier
    clauses: tuple[ClauseId, ...] = Field(min_length=1)


class ClauseOwnership(FrozenModel):
    clause: ClauseId


class Deferral(FrozenModel):
    clause: ClauseId
    target_specification: Identifier
    authority: HumanAuthority


class Supersession(FrozenModel):
    specification: Identifier
    authority: HumanAuthority


class Specification(FrozenModel):
    schema_version: int = Field(ge=1)
    id: Identifier
    version: int = Field(ge=1)
    status: SpecificationStatus
    implementation_authorized: bool
    review: ReviewReference
    decisions: tuple[str, ...] = ()
    plan: str
    ownership: tuple[ClauseOwnership, ...] = ()
    deferrals: tuple[Deferral, ...] = ()
    supersedes: tuple[Supersession, ...] = ()
    intent: tuple[str, ...] = ()
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ownership_defaults_to_review_claims(self) -> "Specification":
        if self.ownership and tuple(item.clause for item in self.ownership) != self.review.clauses:
            raise ValueError("ownership must exactly match the review clause claims")
        return self

    @property
    def owned_clauses(self) -> tuple[ClauseId, ...]:
        if self.ownership:
            return tuple(item.clause for item in self.ownership)
        return self.review.clauses


class PlanObligation(FrozenModel):
    id: Identifier
    clauses: tuple[ClauseId, ...] = Field(min_length=1)
    outcome: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class Plan(FrozenModel):
    schema_version: int = Field(default=1, ge=1)
    id: Identifier
    status: PlanStatus
    specification: str
    approved_base: str = Field(min_length=1)
    obligations: tuple[PlanObligation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_obligations(self) -> "Plan":
        identifiers = [obligation.id for obligation in self.obligations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("plan obligation identifiers must be unique")
        return self


def require_relative_path(value: str) -> PurePosixPath:
    """Return a normalized repository-relative reference or reject it."""
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
        raise ValueError(f"reference is not a repository-relative path: {value}")
    return path
