from datetime import date

import pytest
from pydantic import ValidationError

from reposeal.change.models import (
    Clause,
    Review,
    ReviewSource,
    ReviewStatus,
)


def test_review_is_strict_and_immutable() -> None:
    review = Review(
        schema_version=1,
        id="change",
        status=ReviewStatus.ACTIVE,
        recorded_at=date(2026, 8, 28),
        source=ReviewSource(kind="human", summary="A requirement"),
        clauses=(Clause(id="REQ-1", statement="Observable behavior"),),
    )

    with pytest.raises(ValidationError):
        review.__setattr__("status", ReviewStatus.CLOSED)


def test_review_rejects_duplicate_clause_identifiers() -> None:
    clause = Clause(id="REQ-1", statement="Observable behavior")
    with pytest.raises(ValidationError, match="unique"):
        Review(
            schema_version=1,
            id="change",
            status=ReviewStatus.ACTIVE,
            recorded_at=date(2026, 8, 28),
            source=ReviewSource(kind="human", summary="A requirement"),
            clauses=(clause, clause),
        )
