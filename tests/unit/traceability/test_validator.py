from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from reposeal.change.models import Plan, Review, Specification
from reposeal.traceability.boundary import (
    RepositoryInventory,
    TraceabilityManifest,
)
from reposeal.traceability.loading import (
    load_plan,
    load_review,
    load_specification,
)
from reposeal.traceability.validator import TraceabilityValidator

FIXTURE = Path("tests/fixtures/changes/valid")


def _documents() -> tuple[
    str,
    Review,
    tuple[tuple[str, Specification], ...],
    tuple[tuple[str, Plan], ...],
    RepositoryInventory,
]:
    review_path = "changes/example/review.yaml"
    specification_paths = (
        "changes/example/specs/first.yaml",
        "changes/example/specs/second.yaml",
    )
    plan_paths = (
        "changes/example/plans/first.md",
        "changes/example/plans/second.md",
    )
    paths = frozenset((review_path, *specification_paths, *plan_paths, "decisions/accepted.md"))
    return (
        review_path,
        load_review(FIXTURE / review_path),
        tuple((path, load_specification(FIXTURE / path)) for path in specification_paths),
        tuple((path, load_plan(FIXTURE / path, "example")) for path in plan_paths),
        RepositoryInventory(paths=paths),
    )


def test_complete_change_is_valid() -> None:
    review_path, review, specifications, plans, inventory = _documents()
    report = TraceabilityValidator().validate(
        TraceabilityManifest(schema_version=1),
        inventory,
        review_path,
        review,
        specifications,
        plans,
    )
    assert report.valid
    assert report.issues == ()


@given(st.sampled_from(["REQ-1", "REQ-2"]))
def test_removing_an_owner_is_always_detected(clause: str) -> None:
    review_path, review, specifications, plans, inventory = _documents()
    kept = tuple(item for item in specifications if clause not in item[1].owned_clauses)
    report = TraceabilityValidator().validate(
        TraceabilityManifest(schema_version=1),
        inventory,
        review_path,
        review,
        kept,
        plans,
    )
    assert "missing-owner" in {issue.code for issue in report.issues}


@given(st.sampled_from(["REQ-1", "REQ-2"]))
def test_removing_plan_coverage_is_always_detected(clause: str) -> None:
    review_path, review, specifications, plans, inventory = _documents()
    changed_plans = tuple(
        (path, plan.model_copy(update={"obligations": tuple()}))
        if any(clause in obligation.clauses for obligation in plan.obligations)
        else (path, plan)
        for path, plan in plans
    )
    report = TraceabilityValidator().validate(
        TraceabilityManifest(schema_version=1),
        inventory,
        review_path,
        review,
        specifications,
        changed_plans,
    )
    assert "missing-obligation" in {issue.code for issue in report.issues}


def test_repository_plan_status_phrases_map_to_typed_lifecycle_states(tmp_path: Path) -> None:
    approved = tmp_path / "approved.md"
    approved.write_text(
        "# Plan\n\nStatus: approved for implementation\n"
        "Specification: `changes/example/specs/first.yaml`\nBase: `abc`\n\n"
        "## Obligations\n\n| ID | Clauses | Outcome |\n| --- | --- | --- |\n"
        "| OBL-1 | REQ-1 | Complete it. |\n",
        encoding="utf-8",
    )
    future = tmp_path / "future.md"
    future.write_text(
        approved.read_text(encoding="utf-8").replace(
            "approved for implementation", "future downstream plan; implementation blocked"
        ),
        encoding="utf-8",
    )

    assert load_plan(approved, "example").status.value == "approved"
    assert load_plan(future, "example").status.value == "draft"
