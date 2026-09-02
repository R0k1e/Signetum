"""Typed observations and immutable status projections."""

from enum import StrEnum
from typing import Protocol

from signetum.change.models import ClauseId, FrozenModel, Identifier


class DerivedState(StrEnum):
    SPECIFIED = "specified"
    IMPLEMENTING = "implementing"
    READY = "ready"
    INTEGRATED = "integrated"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    REOPENED = "reopened"
    EXCLUDED = "excluded"


class MemberObservation(FrozenModel):
    plan_id: Identifier
    commit: str
    ready: bool


class IntegrationObservation(FrozenModel):
    member_commit: str
    batch_commit: str


class DeliveryObservation(FrozenModel):
    batch_commit: str
    delivery_commit: str


class EvidenceSnapshot(FrozenModel):
    members: tuple[MemberObservation, ...] = ()
    integrations: tuple[IntegrationObservation, ...] = ()
    deliveries: tuple[DeliveryObservation, ...] = ()


class EvidenceProvider(Protocol):
    def observe(self, _repository_identity: str) -> EvidenceSnapshot:
        """Return typed observations bound to exact repository identities."""


class ClauseProjection(FrozenModel):
    clause: ClauseId
    state: DerivedState
    specification: Identifier | None
    plan: Identifier | None
    commit: str | None
    delivery_commit: str | None


class StatusProjection(FrozenModel):
    schema_version: int = 1
    review: Identifier
    state: DerivedState
    clauses: tuple[ClauseProjection, ...]
