"""One structured change record with a content-bound human approval.

This boundary checks record structure and the recorded approval binding. It
does not grant approval, validate external decision standing or publish evidence.
"""

import argparse
import hashlib
import json
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from signetum.change.models import ClauseId, Identifier, ReviewSource
from signetum.contract_values import FrozenContract
from signetum.decision_clauses import Text, Version
from signetum.decision_history import DecisionTransaction
from signetum.serialization import Constraints, contract_mapping, dataclass_from_mapping

Digest = Annotated[str, Constraints(pattern="^sha256:[0-9a-f]{64}$")]


@dataclass(frozen=True, kw_only=True)
class Requirement(FrozenContract):
    id: ClauseId
    outcome: Text
    acceptance: Annotated[tuple[Text, ...], Constraints(min_length=1)]


@dataclass(frozen=True, kw_only=True)
class ExcludedScope(FrozenContract):
    statement: Text
    reason: Text


@dataclass(frozen=True, kw_only=True)
class TransferredRequirement(FrozenContract):
    id: ClauseId
    statement: Text
    target: Identifier


@dataclass(frozen=True, kw_only=True)
class ExecutionAutonomy(FrozenContract):
    allowed: tuple[Text, ...] = ()
    requires_confirmation: tuple[Text, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EvidenceRetirement(FrozenContract):
    id: Identifier
    target: Identifier
    resolution_id: Identifier
    targets: Annotated[tuple[Text, ...], Constraints(min_length=1)]
    reason: Text


@dataclass(frozen=True, kw_only=True)
class ChangeContract(FrozenContract):
    version: Version
    approved_base: Text
    requirements: Annotated[tuple[Requirement, ...], Constraints(min_length=1)]
    autonomy: ExecutionAutonomy = field(default_factory=ExecutionAutonomy)
    excluded: tuple[ExcludedScope, ...] = ()
    transferred: tuple[TransferredRequirement, ...] = ()
    decisions: tuple[DecisionTransaction, ...] = ()
    retirements: tuple[EvidenceRetirement, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ExecutionStep(FrozenContract):
    id: ClauseId
    requirements: Annotated[tuple[ClauseId, ...], Constraints(min_length=1)]
    action: Text


@dataclass(frozen=True, kw_only=True)
class ExecutionPlan(FrozenContract):
    steps: Annotated[tuple[ExecutionStep, ...], Constraints(min_length=1)]


@dataclass(frozen=True, kw_only=True)
class RecordedApproval(FrozenContract):
    actor: Text
    recorded_at: date
    source: Text
    contract_digest: Digest


@dataclass(frozen=True, kw_only=True)
class ChangeRecord(FrozenContract):
    schema_version: Literal[1]
    id: ClauseId
    source: ReviewSource
    contract: ChangeContract
    execution: ExecutionPlan
    approval: RecordedApproval | None = None
    status: Literal["active", "complete", "withdrawn"] = "active"


def contract_digest(contract: ChangeContract) -> str:
    encoded = json.dumps(
        contract_mapping(contract), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_change_record(record: ChangeRecord) -> None:
    """Check exhaustive planning and prevent approval surviving changed behavior."""
    requirements = {item.id for item in record.contract.requirements}
    if record.status == "complete" and record.approval is None:
        raise ValueError("a completed change requires a recorded approval")
    transfers = {item.id for item in record.contract.transferred}
    if (
        len(requirements) != len(record.contract.requirements)
        or (len(transfers) != len(record.contract.transferred))
        or requirements & transfers
    ):
        raise ValueError("requirement ownership must be unique")
    steps = {item.id for item in record.execution.steps}
    if len(steps) != len(record.execution.steps):
        raise ValueError("execution step identities must be unique")
    owned = {identity for step in record.execution.steps for identity in step.requirements}
    if owned != requirements:
        raise ValueError("execution steps must cover exactly the owned requirements")
    for event in record.contract.decisions:
        if event.change_id != record.id:
            raise ValueError("decision transaction belongs to a different change")
    if record.approval is not None:
        if record.approval.contract_digest != contract_digest(record.contract):
            raise ValueError("recorded approval does not bind the current contract")


def parse_change_record(source: str) -> ChangeRecord:
    document = tomllib.loads(source)
    if set(document) != {"change"}:
        raise ValueError("change record requires exactly one change document")
    record = dataclass_from_mapping(ChangeRecord, document["change"], use_defaults=True)
    validate_change_record(record)
    return record


def approval_view(record: ChangeRecord) -> dict[str, object]:
    validate_change_record(record)
    return {
        "schema_version": 1,
        "change_id": record.id,
        "stage": (
            record.status
            if record.status != "active"
            else "approved"
            if record.approval is not None
            else "draft"
        ),
        "contract_digest": contract_digest(record.contract),
        "source": contract_mapping(record.source),
        "contract": contract_mapping(record.contract),
        "execution": contract_mapping(record.execution),
        "approval": contract_mapping(record.approval) if record.approval is not None else None,
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parsed = parser.parse_args(arguments)
    try:
        result = approval_view(parse_change_record(parsed.record.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as error:
        print(
            json.dumps({"schema_version": 1, "status": "invalid", "reason": str(error)}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
