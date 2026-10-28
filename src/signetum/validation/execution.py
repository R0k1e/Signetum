"""Execution adapter for exact validation identities and shard commands."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Protocol

from pydantic import JsonValue

from signetum.evidence.receipts import (
    ArtifactIdentity,
    EvidenceIdentity,
    EvidenceReceipt,
    ShardOutcome,
    ToolIdentity,
    ValidationSelection,
    combine_shard_evidence,
)
from signetum.findings import Finding
from signetum.validation import ToolDeclaration, ValidationGraph, ValidationShard
from signetum.waivers import Waiver, cover_findings


class ValidationExecutionError(ValueError):
    """A declared tool or shard could not produce successful evidence."""


class ValidationInfrastructureError(ValidationExecutionError):
    """Validation inputs or tools were unavailable, so no verdict was obtained."""


@dataclass(frozen=True)
class ShardExecution:
    """One shard command's verdict and, when it failed, what it reported."""

    succeeded: bool
    diagnostic: str = ""
    recovered: tuple[dict[str, JsonValue], ...] = ()


class ValidationAdapter(Protocol):
    """Repository-owned effects required by the generic execution engine."""

    def commit_identity(self) -> str:
        """Return the exact commit being observed."""

    def tree_identity(self) -> str:
        """Return the exact Git tree being observed."""

    def read_file(self, path: str) -> bytes:
        """Read one declared repository-relative file from the observed tree."""

    def identify_tool(self, tool: ToolDeclaration) -> str:
        """Execute the declared identity command and return its stable output."""

    def run_shard(self, shard: ValidationShard) -> ShardExecution:
        """Execute one shard command and return its verdict."""

    def report_findings(self, shard: ValidationShard) -> tuple[Finding, ...]:
        """Execute a world shard's findings command and parse its document."""


@dataclass(frozen=True)
class ValidationInputs:
    """Explicit Core projection used to build one evidence identity."""

    configuration_path: str
    profiles: tuple[str, ...]
    lockfiles: tuple[str, ...]
    tools: tuple[ToolDeclaration, ...]
    base: str | None = None
    selection: ValidationSelection | None = None
    schema_digest: str = "sha256:" + "0" * 64
    waivers: tuple[Waiver, ...] = field(default=())
    today: date | None = None
    recovery_history: tuple[frozenset[str], ...] = ()
    recovery_threshold: int = 3
    recovery_window: int = 20

    def __post_init__(self) -> None:
        if self.recovery_window < 1 or self.recovery_threshold < 1:
            raise ValidationExecutionError("recovery window and threshold must be positive")
        if self.configuration_path != "signetum.toml":
            raise ValidationExecutionError("configuration path must be signetum.toml")
        if self.profiles != tuple(sorted(set(self.profiles))):
            raise ValidationExecutionError("profile inputs must be unique and sorted")
        if self.lockfiles != tuple(sorted(set(self.lockfiles))):
            raise ValidationExecutionError("lockfile inputs must be unique and sorted")
        if len(self.tools) != len({tool.name for tool in self.tools}):
            raise ValidationExecutionError("tool inputs must have unique names")


def build_evidence_identity(
    graph: ValidationGraph, inputs: ValidationInputs, adapter: ValidationAdapter
) -> EvidenceIdentity:
    """Observe every exact input before any shard executes."""

    configuration = ArtifactIdentity.from_bytes(
        inputs.configuration_path, adapter.read_file(inputs.configuration_path)
    )
    lockfiles = tuple(
        sorted(
            ArtifactIdentity.from_bytes(path, adapter.read_file(path)) for path in inputs.lockfiles
        )
    )
    tools = tuple(
        sorted(ToolIdentity(tool.name, adapter.identify_tool(tool)) for tool in inputs.tools)
    )
    return EvidenceIdentity(
        commit=adapter.commit_identity(),
        tree=adapter.tree_identity(),
        base=inputs.base,
        configuration=configuration,
        profiles=inputs.profiles,
        graph=graph.digest,
        lockfiles=lockfiles,
        tools=tools,
    )


def _resolve_outcome(
    shard: ValidationShard,
    inputs: ValidationInputs,
    adapter: ValidationAdapter,
    *,
    today: date,
    recovered: list[dict[str, JsonValue]],
) -> ShardOutcome:
    """Execute one shard and decide whether it produced reusable evidence."""

    observed_at = datetime.now(UTC).isoformat() if shard.evidence == "world" else None
    execution = adapter.run_shard(shard)
    if execution.succeeded:
        recovered.extend({**defect, "shard": shard.name} for defect in execution.recovered)
        return ShardOutcome(shard.name, shard.digest, shard.evidence, "passed", observed_at)
    if shard.evidence != "world":
        raise ValidationExecutionError(
            execution.diagnostic or f"validation shard failed: {shard.name}"
        )
    if not shard.findings_command:
        raise ValidationExecutionError(
            f"world shard failed and declares no findings command: {shard.name}"
        )
    coverage = cover_findings(
        shard.name, adapter.report_findings(shard), inputs.waivers, today=today
    )
    if not coverage.covered:
        raise ValidationExecutionError(coverage.diagnostic(shard.name))
    return ShardOutcome(
        shard.name,
        shard.digest,
        "world",
        "waived",
        observed_at,
        coverage.waivers,
        coverage.findings,
    )


def execute_gate(
    graph: ValidationGraph,
    gate: str,
    inputs: ValidationInputs,
    adapter: ValidationAdapter,
) -> EvidenceReceipt:
    """Execute one resolved gate and compose only its successful shard evidence.

    Every shard whose dependencies held is executed even after an earlier shard
    failed, so one run reports every independent problem it can observe.
    """

    identity = build_evidence_identity(graph, inputs, adapter)
    today = inputs.today or datetime.now(UTC).date()
    shard_by_name = {shard.name: shard for shard in graph.shards}
    receipts: list[EvidenceReceipt] = []
    failures: list[str] = []
    unproven: set[str] = set()
    recovered: list[dict[str, JsonValue]] = []
    for name in graph.execution_order(gate):
        shard = shard_by_name[name]
        blocked = sorted(unproven.intersection(shard.requires))
        if blocked:
            unproven.add(name)
            failures.append(f"{name}: skipped after {', '.join(blocked)}")
            continue
        try:
            outcome = _resolve_outcome(shard, inputs, adapter, today=today, recovered=recovered)
        except ValidationExecutionError as error:
            unproven.add(name)
            failures.append(str(error))
            continue
        receipts.append(
            EvidenceReceipt.shard(
                identity=identity,
                shard=outcome,
                protocol="reposeal.validation-evidence@3",
                schema_digest=inputs.schema_digest,
                selection=inputs.selection,
            )
        )
    if failures:
        raise ValidationExecutionError("; ".join(failures))
    if gate == "member":
        require_recovery_limit(recovered, inputs)
    receipt = combine_shard_evidence(
        gate=gate,
        required_shards=graph.execution_order(gate),
        receipts=tuple(receipts),
    )
    if recovered:
        return replace(
            receipt,
            extensions={
                "recovered_flake_defects": [
                    {**defect, "gate": gate, "source": identity.commit} for defect in recovered
                ]
            },
        )
    return receipt


def require_recovery_limit(defects: JsonValue, inputs: ValidationInputs) -> None:
    """A final receipt used for member admission cannot bypass recovery policy."""
    if not isinstance(defects, list):
        raise ValidationExecutionError("invalid recovered robustness defects")
    repeated = []
    for defect in defects:
        if (
            not isinstance(defect, dict)
            or not isinstance(defect.get("shard"), str)
            or not isinstance(defect.get("node_id"), str)
        ):
            raise ValidationExecutionError("invalid recovered robustness defect")
        key = f"{defect['shard']}::{defect['node_id']}"
        count = 1 + sum(key in history for history in inputs.recovery_history)
        if count >= inputs.recovery_threshold:
            repeated.append(f"{key} recoveries={count}")
    if repeated:
        raise ValidationExecutionError(
            "repeated recovered robustness defect: "
            + "; ".join(repeated)
            + "; first_failures="
            + json.dumps(defects, sort_keys=True)
        )


__all__ = [
    "ShardExecution",
    "ValidationAdapter",
    "ValidationExecutionError",
    "ValidationInputs",
    "build_evidence_identity",
    "execute_gate",
]
