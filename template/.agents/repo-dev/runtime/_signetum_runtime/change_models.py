# Generated from signetum.change.models; edit the engine source and regenerate.
"""Versioned, immutable models for requirement closure."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated

from .contract_values import FrozenContract
from .serialization import Constraints

Identifier = Annotated[str, Constraints(min_length=1, pattern="^[A-Za-z0-9][A-Za-z0-9._/-]*$")]
ClauseId = Annotated[str, Constraints(min_length=1, pattern="^[A-Za-z0-9][A-Za-z0-9._-]*$")]


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


def complete_decision_replacements(
    decision: Decision, decisions_by_name: Mapping[str, Decision]
) -> tuple[str, ...]:
    """Partial successors preserve the unaffected authority of the old decision."""
    return tuple(
        reference
        for reference in decision.superseded_by
        if (successor := decisions_by_name.get(reference.rsplit("/", 1)[-1])) is None
        or decision.name not in successor.partially_supersedes
    )


def require_relative_path(value: str) -> PurePosixPath:
    """Return a normalized repository-relative reference or reject it."""
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
        raise ValueError(f"reference is not a repository-relative path: {value}")
    return path
