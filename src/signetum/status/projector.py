"""Pure derived-state projection from contracts and typed evidence."""

from pathlib import PurePosixPath

from signetum.change.models import AcceptanceResult, ClauseDisposition, Plan, Review, Specification
from signetum.change_record import ChangeRecord
from signetum.status.models import (
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
    excluded = {
        item.id for item in review.clauses if item.disposition is ClauseDisposition.OUT_OF_SCOPE
    }
    accepted = set(review.acceptance.accepted_clauses)
    reopened = (
        set(review.acceptance.rejected_clauses)
        if review.acceptance.result in {AcceptanceResult.REJECTED, AcceptanceResult.REOPENED}
        else set()
    )
    clauses: list[ClauseProjection] = []
    for clause in review.clauses:
        owner = owners.get(clause.id)
        plan = (
            plans_by_specification.get(owner.id.rpartition("/")[2]) if owner is not None else None
        )
        state, commit, delivery_commit = _execution_progress(
            plan.id if plan is not None else None, evidence
        )
        if (
            delivery_commit is not None
            and review.acceptance.delivery_commit == delivery_commit
            and clause.id in accepted
        ):
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


def _execution_progress(
    plan: str | None, evidence: EvidenceSnapshot
) -> tuple[DerivedState, str | None, str | None]:
    state = DerivedState.IMPLEMENTING if plan is not None else DerivedState.SPECIFIED
    member = next((item for item in reversed(evidence.members) if item.plan_id == plan), None)
    if member is None or not member.ready:
        return state, None, None
    batch = next(
        (
            item.batch_commit
            for item in reversed(evidence.integrations)
            if item.member_commit == member.commit
        ),
        None,
    )
    delivered = (
        next(
            (
                item.delivery_commit
                for item in reversed(evidence.deliveries)
                if item.batch_commit == batch
            ),
            None,
        )
        if batch is not None
        else None
    )
    if delivered is not None:
        return DerivedState.DELIVERED, delivered, delivered
    if batch is not None:
        return DerivedState.INTEGRATED, batch, None
    return DerivedState.READY, member.commit, None


def project_record_status(
    path: str, record: ChangeRecord, evidence: EvidenceSnapshot
) -> StatusProjection:
    plan = path if record.approval is not None and record.status != "withdrawn" else None
    state, commit, delivered = _execution_progress(plan, evidence)
    clauses = tuple(
        ClauseProjection(
            clause=item.id,
            state=state,
            specification=path,
            plan=plan,
            commit=commit,
            delivery_commit=delivered,
        )
        for item in record.contract.requirements
    )
    transfers = tuple(
        ClauseProjection(
            clause=item.id,
            state=DerivedState.SPECIFIED,
            specification=item.target,
            plan=None,
            commit=None,
            delivery_commit=None,
        )
        for item in record.contract.transferred
    )
    return StatusProjection(
        review=record.id,
        state=DerivedState.SPECIFIED if transfers else state,
        clauses=clauses + transfers,
    )
