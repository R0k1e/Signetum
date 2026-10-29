# Generated from signetum.development_log; edit the engine source and regenerate.
"""Significant source history, resolution repair and derived current decisions."""

from dataclasses import dataclass
from typing import Annotated, Literal

from .change_models import ClauseId, Identifier, require_relative_path
from .change_record import Digest, EvidenceRetirement
from .contract_values import FrozenContract
from .decision_clauses import Text
from .decision_history import (
    DecisionTransaction,
    DecisionWorkingSet,
    project_decision_history,
)
from .serialization import Constraints

ObjectId = Annotated[str, Constraints(pattern="^[0-9a-f]{40}(?:[0-9a-f]{24})?$")]


@dataclass(frozen=True, kw_only=True)
class DevelopmentObservation(FrozenContract):
    id: Identifier
    requirements: Annotated[tuple[ClauseId, ...], Constraints(min_length=1)]
    summary: Text
    reason: Text
    evidence: tuple[Text, ...] = ()


@dataclass(frozen=True, kw_only=True)
class DevelopmentResolution(FrozenContract):
    id: Identifier
    target: Identifier
    status: Literal["resolved", "rejected", "deferred"]
    reason: Text
    evidence: tuple[Text, ...] = ()
    followup: Text | None = None


@dataclass(frozen=True, kw_only=True)
class ResolutionRetraction(FrozenContract):
    id: Identifier
    target: Identifier
    resolution_id: Identifier
    reason: Text


@dataclass(frozen=True, kw_only=True)
class DevelopmentTransaction(FrozenContract):
    id: Identifier
    change_id: ClauseId
    approval_digest: Digest
    operation: Literal["record", "resolve", "retract", "reconcile", "retire"]
    reason: Text
    observations: tuple[DevelopmentObservation, ...] = ()
    resolutions: tuple[DevelopmentResolution, ...] = ()
    retractions: tuple[ResolutionRetraction, ...] = ()
    retirements: tuple[EvidenceRetirement, ...] = ()
    decisions: tuple[DecisionTransaction, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ApprovalProof(FrozenContract):
    commit: ObjectId
    path: Text
    blob: ObjectId


@dataclass(frozen=True, kw_only=True)
class DevelopmentEntry(FrozenContract):
    schema_version: Literal[1] = 1
    sequence: Annotated[int, Constraints(minimum=1)]
    previous_digest: Digest
    approval: ApprovalProof
    transaction: DevelopmentTransaction


@dataclass(frozen=True, kw_only=True)
class WithdrawnResolution(FrozenContract):
    resolution: DevelopmentResolution
    retraction: ResolutionRetraction
    source_event: Identifier
    approval: ApprovalProof


@dataclass(frozen=True, kw_only=True)
class AppliedRetirement(FrozenContract):
    retirement: EvidenceRetirement
    source_event: Identifier
    approval: ApprovalProof


@dataclass(frozen=True, kw_only=True)
class ObservationState(FrozenContract):
    observation: DevelopmentObservation
    change_id: ClauseId
    source_event: Identifier
    approval: ApprovalProof
    status: Literal["pending", "resolved", "rejected", "deferred"]
    resolution: DevelopmentResolution | None = None
    resolution_event: Identifier | None = None
    retractions: tuple[WithdrawnResolution, ...] = ()
    retirements: tuple[AppliedRetirement, ...] = ()
    effective_evidence: tuple[Text, ...] = ()


@dataclass(frozen=True, kw_only=True)
class DevelopmentSnapshot(FrozenContract):
    schema_version: Literal[1] = 1
    history_digest: Digest
    entries: tuple[DevelopmentEntry, ...]
    observations: tuple[ObservationState, ...]
    working_set: DecisionWorkingSet


def transaction_identities(transaction: DevelopmentTransaction) -> tuple[str, ...]:
    return (
        transaction.id,
        *(item.id for item in transaction.observations),
        *(item.id for item in transaction.resolutions),
        *(item.id for item in transaction.retractions),
        *(item.id for item in transaction.retirements),
        *(item.id for item in transaction.decisions),
        *(edit.id for item in transaction.decisions for edit in item.clauses),
    )


def validate_resolution(resolution: DevelopmentResolution) -> None:
    if resolution.status == "deferred" and not resolution.followup:
        raise ValueError("deferred work requires an active follow-up requirement")
    if resolution.status != "deferred" and resolution.followup is not None:
        raise ValueError("only deferred work can name a follow-up requirement")
    if resolution.status == "resolved" and not resolution.evidence:
        raise ValueError("resolved work requires acceptance evidence")


def validate_transaction(
    transaction: DevelopmentTransaction, *, judge_resolutions: bool = True
) -> None:
    owned = transaction_identities(transaction)
    if len(owned) != len(set(owned)):
        raise ValueError("development event identities must be unique")
    for identity in owned:
        if require_relative_path(identity).as_posix() != identity or not identity.startswith(
            transaction.change_id + "/"
        ):
            raise ValueError("development event identity belongs to a different change")
    payloads = {
        "observations": transaction.observations,
        "resolutions": transaction.resolutions,
        "retractions": transaction.retractions,
        "retirements": transaction.retirements,
        "decisions": transaction.decisions,
    }
    if not any(payloads.values()):
        raise ValueError("development transaction is empty")
    allowed = {
        "record": {"observations"},
        "resolve": {"resolutions"},
        "retract": {"retractions"},
        "retire": {"retirements"},
        "reconcile": set(payloads),
    }[transaction.operation]
    if any(value and key not in allowed for key, value in payloads.items()):
        raise ValueError("operation cannot carry these development changes")
    for item in transaction.observations:
        if len(set(item.requirements)) != len(item.requirements):
            raise ValueError("observation requirements must be unique")
    if judge_resolutions:
        for resolution in transaction.resolutions:
            validate_resolution(resolution)
    if any(item.change_id != transaction.change_id for item in transaction.decisions):
        raise ValueError("decision transaction belongs to a different change")


def resolution_index(
    entries: tuple[DevelopmentEntry, ...],
) -> dict[str, DevelopmentResolution]:
    return {item.id: item for entry in entries for item in entry.transaction.resolutions}


def withdrawn_resolution_ids(entries: tuple[DevelopmentEntry, ...]) -> frozenset[str]:
    return frozenset(
        item.resolution_id for entry in entries for item in entry.transaction.retractions
    )


def project_development_history(
    entries: tuple[DevelopmentEntry, ...], history_digest: str
) -> DevelopmentSnapshot:
    """Withdraw wrong answers before judging what remains; never erase a finding."""
    identities: set[str] = set()
    observed: dict[str, tuple[DevelopmentObservation, DevelopmentEntry]] = {}
    resolutions: dict[str, tuple[DevelopmentResolution, DevelopmentEntry]] = {}
    retracted: dict[str, tuple[ResolutionRetraction, DevelopmentEntry]] = {}
    retired: list[AppliedRetirement] = []
    decisions = []
    for entry in entries:
        transaction = entry.transaction
        validate_transaction(transaction, judge_resolutions=False)
        named = transaction_identities(transaction)
        if identities.intersection(named):
            raise ValueError("duplicate identity in development history")
        identities.update(named)
        for observation in transaction.observations:
            observed[observation.id] = observation, entry
        for resolution in transaction.resolutions:
            resolutions[resolution.id] = resolution, entry
        for retraction in transaction.retractions:
            if retraction.resolution_id in retracted:
                raise ValueError("a resolution cannot be retracted a second time")
            retracted[retraction.resolution_id] = retraction, entry
        retired.extend(
            AppliedRetirement(retirement=item, source_event=transaction.id, approval=entry.approval)
            for item in transaction.retirements
        )
        decisions.extend(transaction.decisions)
    for resolution, _ in resolutions.values():
        if resolution.target not in observed:
            raise ValueError("resolution names an absent observation")
    for identity, (retraction, _) in retracted.items():
        if identity not in resolutions or resolutions[identity][0].target != retraction.target:
            raise ValueError("retraction requires an exact existing resolution of its observation")
    retired_pairs: set[tuple[str, str]] = set()
    for applied in retired:
        retirement = applied.retirement
        original = resolutions.get(retirement.resolution_id)
        if original is None or original[0].target != retirement.target:
            raise ValueError("retirement requires an exact existing resolution")
        if len(set(retirement.targets)) != len(retirement.targets) or not set(
            retirement.targets
        ) <= set(original[0].evidence):
            raise ValueError("retirement can remove only the resolution's named evidence")
        pairs = {(retirement.resolution_id, target) for target in retirement.targets}
        if pairs & retired_pairs:
            raise ValueError("resolution evidence cannot be retired twice")
        retired_pairs.update(pairs)
    states = []
    for identity in sorted(observed):
        observation, entry = observed[identity]
        standing = [
            (value, origin)
            for key, (value, origin) in resolutions.items()
            if value.target == identity and key not in retracted
        ]
        if len(standing) > 1:
            raise ValueError("an observation has more than one standing resolution")
        terminal = standing[0] if standing else None
        if terminal:
            validate_resolution(terminal[0])
        withdrawals = tuple(
            WithdrawnResolution(
                resolution=resolutions[key][0],
                retraction=withdrawal,
                source_event=source.transaction.id,
                approval=source.approval,
            )
            for key, (withdrawal, source) in retracted.items()
            if withdrawal.target == identity
        )
        retirements = tuple(item for item in retired if item.retirement.target == identity)
        effective = []
        if terminal:
            current = terminal[0]
            effective.extend(
                target for target in current.evidence if (current.id, target) not in retired_pairs
            )
            effective.extend(
                item.approval.path
                for item in retirements
                if item.retirement.resolution_id == current.id
            )
        states.append(
            ObservationState(
                observation=observation,
                change_id=entry.transaction.change_id,
                source_event=entry.transaction.id,
                approval=entry.approval,
                status=terminal[0].status if terminal else "pending",
                resolution=terminal[0] if terminal else None,
                resolution_event=terminal[1].transaction.id if terminal else None,
                retractions=withdrawals,
                retirements=retirements,
                effective_evidence=tuple(dict.fromkeys(effective)),
            )
        )
    return DevelopmentSnapshot(
        history_digest=history_digest,
        entries=entries,
        observations=tuple(states),
        working_set=project_decision_history(tuple(decisions)),
    )
