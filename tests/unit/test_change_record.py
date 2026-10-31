"""Core approval, ownership and progress matrices do not require a repository."""

from dataclasses import replace
from datetime import date

import pytest
from change_fixtures import approved_record_source
from signetum import change_record as records
from signetum.change_record import (
    EvidenceRetirement,
    RecordedApproval,
    approval_view,
    contract_digest,
    parse_change_record,
    review_view,
    validate_change_record,
)
from signetum.status import models as states
from signetum.status import projector


def test_recorded_approval_binds_behavior_but_not_routine_plan_refinement(record_source):
    record = parse_change_record(record_source)
    approved = replace(
        record,
        approval=RecordedApproval(
            actor="Owner",
            recorded_at=date(2026, 10, 29),
            source="Owner confirmation in review.",
            contract_digest=contract_digest(record.contract),
        ),
    )
    assert approval_view(approved)["stage"] == "approved"
    step = replace(approved.execution.steps[0], action="Use the same owner and a narrower test.")
    refined = replace(approved, execution=replace(approved.execution, steps=(step,)))
    validate_change_record(refined)
    changed = replace(record.contract.requirements[0], outcome="A different behavior.")
    with pytest.raises(ValueError, match="does not bind"):
        validate_change_record(
            replace(approved, contract=replace(record.contract, requirements=(changed,)))
        )


@pytest.mark.parametrize("damage", ["missing", "unknown", "duplicate"])
def test_steps_cannot_omit_invent_or_duplicate_requirement_ownership(record_source, damage):
    record = parse_change_record(record_source)
    if damage == "duplicate":
        record = replace(
            record, contract=replace(record.contract, requirements=record.contract.requirements * 2)
        )
    else:
        steps = (record.execution.steps[0],)
        if damage == "unknown":
            steps = (replace(steps[0], requirements=("UNKNOWN",)),)
        else:
            second = replace(record.contract.requirements[0], id="REQ-2")
            record = replace(
                record,
                contract=replace(
                    record.contract, requirements=(*record.contract.requirements, second)
                ),
            )
        record = replace(record, execution=replace(record.execution, steps=steps))
    with pytest.raises(ValueError, match=r"ownership|owned requirements"):
        validate_change_record(record)


@pytest.mark.parametrize("boundary", ["base", "autonomy", "excluded"])
def test_recorded_approval_cannot_survive_a_changed_execution_boundary(record_source, boundary):
    record = parse_change_record(record_source)
    approval = RecordedApproval(
        actor="Owner",
        recorded_at=date(2026, 10, 29),
        source="Owner confirmation.",
        contract_digest=contract_digest(record.contract),
    )
    if boundary == "base":
        changed = replace(record.contract, approved_base="another-base")
    elif boundary == "autonomy":
        changed = replace(
            record.contract, autonomy=replace(record.contract.autonomy, allowed=("publication",))
        )
    else:
        changed = replace(record.contract, excluded=())
    with pytest.raises(ValueError, match="does not bind"):
        validate_change_record(replace(record, contract=changed, approval=approval))


@pytest.mark.parametrize(
    "phase", ["ready", "integrated", "delivered", "complete", "foreign", "draft"]
)
def test_consolidated_progress_requires_matching_evidence_and_never_implies_human_acceptance(
    record_source, phase
):
    source = record_source if phase == "draft" else approved_record_source(record_source)
    record = records.parse_change_record(source)
    path = f"changes/{record.id}/change.toml"
    if phase == "complete":
        record = replace(record, status="complete")
    members = (
        ()
        if phase == "complete"
        else (
            states.MemberObservation(
                plan_id="other/change.toml" if phase == "foreign" else path,
                commit="member",
                ready=True,
            ),
        )
    )
    evidence = states.EvidenceSnapshot(
        members=members,
        integrations=(states.IntegrationObservation(member_commit="member", batch_commit="batch"),)
        if phase in {"integrated", "delivered"}
        else (),
        deliveries=(states.DeliveryObservation(batch_commit="batch", delivery_commit="delivery"),)
        if phase == "delivered"
        else (),
    )
    result = projector.project_record_status(path, record, evidence)
    expected = {"complete": "implementing", "foreign": "implementing", "draft": "specified"}.get(
        phase, phase
    )
    assert result.state == expected
    assert all(item.state == expected for item in result.clauses)
    assert result.state != "accepted"


def test_concise_proposal_shows_the_exact_base_and_retirement_to_be_confirmed(record_source):
    record = parse_change_record(record_source)
    retirement = EvidenceRetirement(
        id=f"{record.id}/retire",
        target=f"{record.id}/finding",
        resolution_id=f"{record.id}/answer",
        targets=("obsolete.py",),
        reason="Remove obsolete evidence while preserving the original answer.",
    )
    record = replace(record, contract=replace(record.contract, retirements=(retirement,)))
    view = review_view(record, require_approval=False)
    assert view["approval"] is None and view["status"] == "proposal"
    assert view["approved_base"] == record.contract.approved_base
    assert view["contract_version"] == record.contract.version
    proposals = view["retirements"]
    assert isinstance(proposals, list)
    proposal = proposals[0]
    assert isinstance(proposal, dict)
    assert proposal["targets"] == ["obsolete.py"]
    assert proposal["reason"] == retirement.reason
