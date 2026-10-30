"""Execution adapter for exact validation identities and shard commands."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Protocol

from signetum.evidence.receipts import (
    ArtifactIdentity,
    EvidenceIdentity,
    EvidenceReceipt,
    JsonValue,
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
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class InheritedEvidence:
    """Adapter-verified ancestor evidence and the test shards permitted to inherit."""

    receipt: EvidenceReceipt
    source_receipt: str
    shards: frozenset[str]


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

    def __post_init__(self) -> None:
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
    details: dict[str, JsonValue],
) -> ShardOutcome:
    """Execute one shard and decide whether it produced reusable evidence."""

    observed_at = datetime.now(UTC).isoformat() if shard.evidence == "world" else None
    execution = adapter.run_shard(shard)
    if execution.details:
        details[shard.name] = execution.details
    if execution.succeeded:
        require_original_success(
            [{**defect, "shard": shard.name} for defect in execution.recovered]
        )
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


@dataclass
class _ExecutionResult:
    outcomes: list[ShardOutcome] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    inherited: list[str] = field(default_factory=list)
    recovered: list[dict[str, JsonValue]] = field(default_factory=list)
    details: dict[str, JsonValue] = field(default_factory=dict)
    advisories: list[dict[str, str]] = field(default_factory=list)


def _execute_shards(
    graph: ValidationGraph,
    gate: str,
    inputs: ValidationInputs,
    adapter: ValidationAdapter,
    *,
    reusable: dict[str, ShardOutcome] | None = None,
    executed: set[str] | None = None,
    advisory_world: bool = False,
) -> _ExecutionResult:
    """One verdict owner for qualified execution and non-qualifying diagnostics."""
    result = _ExecutionResult()
    outcomes, names, inherited_names = result.outcomes, result.names, result.inherited
    recovered, shard_details, advisories = result.recovered, result.details, result.advisories
    reusable = reusable or {}
    proven = executed if executed is not None else set()
    shard_by_name = {shard.name: shard for shard in graph.shards}
    today = inputs.today or datetime.now(UTC).date()
    failures: list[str] = []
    validation_failed = False
    unproven: set[str] = set()
    for name in graph.execution_order(gate):
        shard = shard_by_name[name]
        blocked = sorted(unproven.intersection(shard.requires))
        if blocked:
            unproven.add(name)
            failures.append(f"{name}: skipped after {', '.join(blocked)}")
            continue
        if executed is not None and shard.evidence == "tree" and shard.digest in proven:
            continue
        names.append(name)
        try:
            if shard.inherit and name in reusable and reusable[name].command_digest == shard.digest:
                outcome = reusable[name]
                inherited_names.append(name)
            else:
                outcome = _resolve_outcome(
                    shard, inputs, adapter, today=today, recovered=recovered, details=shard_details
                )
        except ValidationExecutionError as error:
            if (
                shard.evidence == "world"
                and advisory_world
                and not isinstance(error, ValidationInfrastructureError)
            ):
                advisories.append({"shard": name, "diagnostic": str(error)})
                continue
            unproven.add(name)
            failures.append(str(error))
            validation_failed |= not isinstance(error, ValidationInfrastructureError)
            continue
        outcomes.append(outcome)
        if outcome.evidence == "tree":
            proven.add(shard.digest)
    if failures:
        failure_type = (
            ValidationExecutionError if validation_failed else ValidationInfrastructureError
        )
        raise failure_type("; ".join(failures))
    return result


def execute_gate(
    graph: ValidationGraph,
    gate: str,
    inputs: ValidationInputs,
    adapter: ValidationAdapter,
    *,
    inherited: InheritedEvidence | None = None,
) -> EvidenceReceipt:
    """Execute one resolved gate and compose only its successful shard evidence.

    Every shard whose dependencies held is executed even after an earlier shard
    failed, so one run reports every independent problem it can observe.
    """

    identity = build_evidence_identity(graph, inputs, adapter)
    reusable: dict[str, ShardOutcome] = {}
    if inherited is not None and gate == "member":
        previous = inherited.receipt
        if (
            previous.execution.gates == ("member",)
            and previous.completeness.member
            and previous.schema_digest == inputs.schema_digest
            and replace(previous.identity, commit=identity.commit, tree=identity.tree) == identity
        ):
            reusable = {
                outcome.name: outcome
                for outcome in previous.execution.shards
                if outcome.name in inherited.shards
                and outcome.evidence == "tree"
                and outcome.status == "passed"
            }
    result = _execute_shards(graph, gate, inputs, adapter, reusable=reusable)
    inherited_names, recovered, shard_details = result.inherited, result.recovered, result.details
    receipts = [
        EvidenceReceipt.shard(
            identity=identity,
            shard=outcome,
            protocol="reposeal.validation-evidence@3",
            schema_digest=inputs.schema_digest,
            selection=inputs.selection,
        )
        for outcome in result.outcomes
    ]
    if build_evidence_identity(graph, inputs, adapter) != identity:
        raise ValidationExecutionError("validation inputs changed during execution")
    receipt = combine_shard_evidence(
        gate=gate,
        required_shards=graph.execution_order(gate),
        receipts=tuple(receipts),
    )
    extensions: dict[str, JsonValue] = {}
    if shard_details:
        extensions["shard_details"] = shard_details
    defects: list[JsonValue] = [
        {**defect, "gate": gate, "source": identity.commit} for defect in recovered
    ]
    if inherited_names and inherited is not None:
        extensions["inherited_test_evidence_from"] = {
            "commit": inherited.receipt.identity.commit,
            "receipt": inherited.source_receipt,
            "shards": list(inherited_names),
        }
        prior_defects = inherited.receipt.extensions.get("recovered_flake_defects", [])
        if isinstance(prior_defects, list):
            defects.extend(
                {**defect, "inherited_from": inherited.source_receipt}
                for defect in prior_defects
                if isinstance(defect, dict) and defect.get("shard") in inherited_names
            )
    if defects:
        require_original_success(defects)
        extensions["recovered_flake_defects"] = defects
    if extensions:
        return replace(receipt, extensions=extensions)
    return receipt


def require_original_success(defects: object) -> None:
    """A diagnostic retry cannot authorize current execution or admission."""
    if not isinstance(defects, list):
        raise ValidationExecutionError("invalid recovered robustness defects")
    for defect in defects:
        if (
            not isinstance(defect, dict)
            or not isinstance(defect.get("shard"), str)
            or not isinstance(defect.get("node_id"), str)
        ):
            raise ValidationExecutionError("invalid recovered robustness defect")
    if defects:
        raise ValidationExecutionError(
            "original validation failure cannot be cleared by retry; first_failures="
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


def execute_diagnostic_gate(
    graph: ValidationGraph,
    gate: str,
    adapter: ValidationAdapter,
    *,
    executed: set[str] | None = None,
    advisory_world: bool = False,
    tools: tuple[ToolDeclaration, ...] = (),
    inputs: ValidationInputs | None = None,
) -> dict[str, object]:
    """Execute diagnostics without granting or storing readiness evidence."""
    projected = inputs or ValidationInputs(
        configuration_path="signetum.toml", profiles=(), lockfiles=(), tools=tools
    )
    identity = build_evidence_identity(graph, projected, adapter) if inputs is not None else None
    if inputs is None:
        for tool in tools:
            adapter.identify_tool(tool)
    result = _execute_shards(
        graph, gate, projected, adapter, executed=executed, advisory_world=advisory_world
    )
    if identity is not None and build_evidence_identity(graph, projected, adapter) != identity:
        raise ValidationExecutionError("validation inputs changed during execution")
    return {
        "executed": result.names,
        "advisories": result.advisories,
        "recovered_flake_defects": result.recovered,
        "shard_details": result.details,
        "outcomes": [
            {
                "name": outcome.name,
                "status": outcome.status,
                "waivers": list(outcome.waivers),
                "findings": list(outcome.findings),
            }
            for outcome in result.outcomes
        ],
    }
