from pathlib import Path

from reposeal.status.models import (
    DeliveryObservation,
    DerivedState,
    EvidenceSnapshot,
    IntegrationObservation,
    MemberObservation,
)
from reposeal.status.projector import project_status
from reposeal.traceability.loading import (
    load_plan,
    load_review,
    load_specification,
)

FIXTURE = Path("tests/fixtures/changes/valid")


def test_exact_typed_evidence_projects_accepted_parent() -> None:
    review = load_review(FIXTURE / "changes/example/review.toml")
    specifications = tuple(
        load_specification(FIXTURE / f"changes/example/specs/{name}.toml")
        for name in ("first", "second")
    )
    plans = tuple(
        load_plan(FIXTURE / f"changes/example/plans/{name}.md", "example")
        for name in ("first", "second")
    )
    evidence = EvidenceSnapshot(
        members=tuple(
            MemberObservation(plan_id=plan.id, commit=f"member-{index}", ready=True)
            for index, plan in enumerate(plans, 1)
        ),
        integrations=(
            IntegrationObservation(member_commit="member-1", batch_commit="batch-1"),
            IntegrationObservation(member_commit="member-2", batch_commit="batch-1"),
        ),
        deliveries=(DeliveryObservation(batch_commit="batch-1", delivery_commit="delivery-1"),),
    )

    projection = project_status(review, specifications, plans, evidence)

    assert projection.state is DerivedState.ACCEPTED
    assert {item.state for item in projection.clauses} == {DerivedState.ACCEPTED}


def test_evidence_for_another_commit_does_not_advance_state() -> None:
    review = load_review(FIXTURE / "changes/example/review.toml")
    specification = load_specification(FIXTURE / "changes/example/specs/first.toml")
    plan = load_plan(FIXTURE / "changes/example/plans/first.md", "example")
    evidence = EvidenceSnapshot(
        integrations=(IntegrationObservation(member_commit="other", batch_commit="batch-1"),)
    )
    projection = project_status(review, (specification,), (plan,), evidence)
    first = next(item for item in projection.clauses if item.clause == "REQ-1")
    assert first.state is DerivedState.IMPLEMENTING


def test_pending_acceptance_never_accepts_missing_delivery_evidence() -> None:
    review = load_review(FIXTURE / "changes/example/review.toml")
    specification = load_specification(FIXTURE / "changes/example/specs/first.toml")
    plan = load_plan(FIXTURE / "changes/example/plans/first.md", "example")

    projection = project_status(review, (specification,), (plan,), EvidenceSnapshot())

    assert projection.clauses[0].state is DerivedState.IMPLEMENTING
