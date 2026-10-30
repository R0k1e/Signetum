# Generated from signetum.status.projector; edit the engine source and regenerate.
"""Pure derived-state projection from contracts and typed evidence."""

from .change_record import ChangeRecord
from .status_models import (
    ClauseProjection,
    DerivedState,
    EvidenceSnapshot,
    StatusProjection,
)


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
