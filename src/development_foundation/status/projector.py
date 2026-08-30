"""Pure derived-state projection from contracts and typed evidence."""

from pathlib import PurePosixPath

from development_foundation.change.models import Plan, Review, Specification
from development_foundation.status.models import (
    ClauseProjection,
    DerivedState,
    EvidenceSnapshot,
    StatusProjection,
)

_COMPLETION_RANK = {
    DerivedState.REOPENED: 0,
    DerivedState.SPECIFIED: 1,
    DerivedState.IMPLEMENTING: 2,
    DerivedState.READY: 3,
    DerivedState.INTEGRATED: 4,
    DerivedState.DELIVERED: 5,
    DerivedState.ACCEPTED: 6,
    DerivedState.EXCLUDED: 7,
}


def project_status(
    review: Review,
    specifications: tuple[Specification, ...],
    plans: tuple[Plan, ...],
    evidence: EvidenceSnapshot,
) -> StatusProjection:
    owners = {
        clause: specification
        for specification in specifications
        for clause in specification.owned_clauses
    }
    plans_by_specification = {PurePosixPath(plan.specification).stem: plan for plan in plans}
    members_by_plan = {member.plan_id: member for member in evidence.members}
    integrations = {
        integration.member_commit: integration.batch_commit for integration in evidence.integrations
    }
    deliveries = {
        delivery.batch_commit: delivery.delivery_commit for delivery in evidence.deliveries
    }
    excluded = {item.clause for item in review.exclusions}
    reopened = {item.clause for item in review.reopenings}
    accepted = {
        clause: acceptance.delivery_commit
        for acceptance in review.acceptances
        for clause in acceptance.accepted_clauses
    }
    clauses: list[ClauseProjection] = []
    for clause in review.clauses:
        owner = owners.get(clause.id)
        plan = (
            plans_by_specification.get(owner.id.rpartition("/")[2]) if owner is not None else None
        )
        member = members_by_plan.get(plan.id) if plan is not None else None
        batch_commit = (
            integrations.get(member.commit) if member is not None and member.ready else None
        )
        delivery_commit = deliveries.get(batch_commit) if batch_commit is not None else None
        state = DerivedState.SPECIFIED
        commit = None
        if plan is not None:
            state = DerivedState.IMPLEMENTING
        if member is not None and member.ready:
            state = DerivedState.READY
            commit = member.commit
        if batch_commit is not None:
            state = DerivedState.INTEGRATED
            commit = batch_commit
        if delivery_commit is not None:
            state = DerivedState.DELIVERED
            commit = delivery_commit
        if accepted.get(clause.id) == delivery_commit:
            state = DerivedState.ACCEPTED
        if clause.id in reopened:
            state = DerivedState.REOPENED
        if clause.id in excluded:
            state = DerivedState.EXCLUDED
        clauses.append(
            ClauseProjection(
                clause=clause.id,
                state=state,
                specification=owner.id if owner is not None else None,
                plan=plan.id if plan is not None else None,
                commit=commit,
                delivery_commit=delivery_commit,
            )
        )
    parent_state = min(
        (item.state for item in clauses),
        key=_COMPLETION_RANK.__getitem__,
        default=DerivedState.SPECIFIED,
    )
    return StatusProjection(review=review.id, state=parent_state, clauses=tuple(clauses))
