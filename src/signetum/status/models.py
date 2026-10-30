"""Typed observations and immutable status projections."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from signetum.change.models import ClauseId, Identifier
from signetum.contract_values import FrozenContract


class DerivedState(StrEnum):
    SPECIFIED = "specified"
    IMPLEMENTING = "implementing"
    READY = "ready"
    INTEGRATED = "integrated"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    REOPENED = "reopened"
    EXCLUDED = "excluded"


@dataclass(frozen=True, kw_only=True)
class MemberObservation(FrozenContract):
    plan_id: Identifier
    commit: str
    ready: bool


@dataclass(frozen=True, kw_only=True)
class IntegrationObservation(FrozenContract):
    member_commit: str
    batch_commit: str


@dataclass(frozen=True, kw_only=True)
class DeliveryObservation(FrozenContract):
    batch_commit: str
    delivery_commit: str


@dataclass(frozen=True, kw_only=True)
class EvidenceSnapshot(FrozenContract):
    members: tuple[MemberObservation, ...] = ()
    integrations: tuple[IntegrationObservation, ...] = ()
    deliveries: tuple[DeliveryObservation, ...] = ()


class EvidenceProvider(Protocol):
    def observe(self, _repository_identity: str) -> EvidenceSnapshot:
        """Return typed observations bound to exact repository identities."""


@dataclass(frozen=True, kw_only=True)
class ClauseProjection(FrozenContract):
    clause: ClauseId
    state: DerivedState
    specification: Identifier | None
    plan: Identifier | None
    commit: str | None
    delivery_commit: str | None


@dataclass(frozen=True, kw_only=True)
class StatusProjection(FrozenContract):
    schema_version: int = 1
    review: Identifier
    state: DerivedState
    clauses: tuple[ClauseProjection, ...]
