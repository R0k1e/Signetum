from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from reposeal.change.models import (
    AcceptanceResult,
    ClauseDisposition,
    Decision,
    Plan,
    Review,
    ReviewAcceptance,
    ReviewStatus,
    Specification,
)
from reposeal.traceability.boundary import (
    RepositoryInventory,
    TraceabilityManifest,
)
from reposeal.traceability.loading import (
    load_decision,
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
    tuple[tuple[str, Decision], ...],
]:
    review_path = "changes/example/review.toml"
    specification_paths = (
        "changes/example/specs/first.toml",
        "changes/example/specs/second.toml",
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
        (
            (
                "decisions/accepted.md",
                load_decision(FIXTURE / "decisions/accepted.md", "decisions/accepted.md"),
            ),
        ),
    )


def test_complete_change_is_valid() -> None:
    review_path, review, specifications, plans, inventory, decisions = _documents()
    report = TraceabilityValidator().validate(
        TraceabilityManifest(schema_version=1),
        inventory,
        review_path,
        review,
        specifications,
        plans,
        None,
        decisions,
    )
    assert report.valid
    assert report.issues == ()


@given(st.sampled_from(["REQ-1", "REQ-2"]))
def test_removing_an_owner_is_always_detected(clause: str) -> None:
    review_path, review, specifications, plans, inventory, decisions = _documents()
    kept = tuple(item for item in specifications if clause not in item[1].owned_clauses)
    report = TraceabilityValidator().validate(
        TraceabilityManifest(schema_version=1),
        inventory,
        review_path,
        review,
        kept,
        plans,
        None,
        decisions,
    )
    assert "missing-owner" in {issue.code for issue in report.issues}


@given(st.sampled_from(["REQ-1", "REQ-2"]))
def test_removing_plan_coverage_is_always_detected(clause: str) -> None:
    review_path, review, specifications, plans, inventory, decisions = _documents()
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
        None,
        decisions,
    )
    assert "missing-obligation" in {issue.code for issue in report.issues}


def test_repository_plan_status_phrases_map_to_typed_lifecycle_states(tmp_path: Path) -> None:
    approved = tmp_path / "approved.md"
    approved.write_text(
        "# Plan\n\nStatus: approved for implementation\n"
        "Specification: `changes/example/specs/first.toml`\nBase: `abc`\n\n"
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


def test_out_of_scope_clause_requires_reason_and_no_owner() -> None:
    review_path, review, specifications, plans, inventory, decisions = _documents()
    clause = review.clauses[0].model_copy(update={"disposition": ClauseDisposition.OUT_OF_SCOPE})
    changed = review.model_copy(update={"clauses": (clause, *review.clauses[1:])})

    report = TraceabilityValidator().validate(
        TraceabilityManifest(schema_version=1),
        inventory,
        review_path,
        changed,
        specifications,
        plans,
        None,
        decisions,
    )

    assert {issue.code for issue in report.issues} >= {
        "missing-out-of-scope-reason",
        "out-of-scope-owned",
    }


def test_completed_review_cannot_leave_a_deferred_clause() -> None:
    review_path, review, specifications, plans, inventory, decisions = _documents()
    clause = review.clauses[0].model_copy(update={"disposition": ClauseDisposition.DEFERRED})
    changed = review.model_copy(
        update={"status": ReviewStatus.COMPLETED, "clauses": (clause, *review.clauses[1:])}
    )

    report = TraceabilityValidator().validate(
        TraceabilityManifest(schema_version=1),
        inventory,
        review_path,
        changed,
        specifications,
        plans,
        None,
        decisions,
    )

    assert "unresolved-deferral" in {issue.code for issue in report.issues}


def test_rejection_requires_an_existing_new_change() -> None:
    review_path, review, specifications, plans, inventory, decisions = _documents()
    acceptance = ReviewAcceptance(
        result=AcceptanceResult.REJECTED,
        delivery_commit="delivery-1",
        rejected_clauses=("REQ-1",),
        linked_change="follow-up",
    )
    changed = review.model_copy(update={"acceptance": acceptance})

    report = TraceabilityValidator().validate(
        TraceabilityManifest(schema_version=1),
        inventory,
        review_path,
        changed,
        specifications,
        plans,
        frozenset({"example"}),
        decisions,
    )

    assert "dangling-linked-change" in {issue.code for issue in report.issues}
