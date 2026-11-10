"""Execution adapter for exact validation identities and shard commands."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
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

NodeIdentity = tuple[str, str]
"""One test node as ``(shard, node_id)``."""


@dataclass(frozen=True)
class ShardFailure:
    """One shard of a gate that did not pass, as the failure record and result list it.

    ``exit_code`` is ``None`` when the shard produced no exit status: it was
    stopped at its time bound, its command was unavailable, it was skipped, or
    its verdict came from a ratchet comparison. ``checks`` are the failed check
    names its runner reported; they are reported only, never owed.
    """

    shard: str
    exit_code: int | None = None
    checks: tuple[str, ...] = ()
    skipped_after: tuple[str, ...] = ()

    def document(self) -> dict[str, JsonValue]:
        document: dict[str, JsonValue] = {
            "shard": self.shard,
            "exit_code": self.exit_code,
            "checks": list(self.checks),
        }
        if self.skipped_after:
            document["skipped_after"] = list(self.skipped_after)
        return document

    def summary(self) -> str:
        if self.skipped_after:
            return f"{self.shard} (skipped after {', '.join(self.skipped_after)})"
        status = "no exit status" if self.exit_code is None else f"exit {self.exit_code}"
        return f"{self.shard} ({status}{': ' + ', '.join(self.checks) if self.checks else ''})"


class ValidationExecutionError(ValueError):
    """A declared tool or shard could not produce successful evidence.

    A failed gate carries the nodes its runners reported failing on the first
    attempt, those that passed only on retry, and the shards that passed, so
    the lifecycle can retain diagnostics for the workspace. It also
    carries every shard that did not pass, for the failure record and result.
    """

    def __init__(
        self,
        message: str = "",
        *,
        failed_nodes: tuple[NodeIdentity, ...] = (),
        recovered_nodes: tuple[NodeIdentity, ...] = (),
        passed_shards: tuple[str, ...] = (),
        unreached_nodes: tuple[NodeIdentity, ...] = (),
        failed_shards: tuple[ShardFailure, ...] = (),
    ) -> None:
        super().__init__(message)
        self.failed_nodes = failed_nodes
        self.recovered_nodes = recovered_nodes
        self.passed_shards = passed_shards
        self.unreached_nodes = unreached_nodes
        self.failed_shards = failed_shards


class ValidationInfrastructureError(ValidationExecutionError):
    """Validation inputs or tools were unavailable, so no verdict was obtained."""


@dataclass(frozen=True)
class ShardExecution:
    """One shard command's verdict and, when it failed, what it reported."""

    succeeded: bool
    diagnostic: str = ""
    recovered: tuple[dict[str, JsonValue], ...] = ()
    details: dict[str, JsonValue] = field(default_factory=dict)
    failed_nodes: tuple[str, ...] = ()
    passed_nodes: tuple[str, ...] = ()
    non_failing: dict[str, str] = field(default_factory=dict)
    unreached_nodes: tuple[str, ...] = ()
    """Selected nodes the runner reported it did not run; they fail the shard."""
    exit_code: int | None = None
    """The command's exit status; ``None`` when it produced none."""
    not_collected: tuple[str, ...] | None = None
    failed_checks: tuple[str, ...] = ()
    """Non-test checks the runner reported failing; reported only, never owed."""


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

    def run_shard(
        self, shard: ValidationShard, *, priority_nodes: tuple[str, ...] = ()
    ) -> ShardExecution:
        """Execute one shard command and return its verdict.

        ``priority_nodes`` are optional runner ordering hints; they
        never change what the shard selects or what makes it pass.
        """

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


def require_unchanged_identity(before: EvidenceIdentity, after: EvidenceIdentity) -> None:
    """Name each changed tool, artifact or source identity."""

    def entries(identity: EvidenceIdentity) -> dict[str, object]:
        values = asdict(identity)
        values.pop("tools")
        values.pop("lockfiles")
        values.update({"tool:" + tool.name: tool.identity for tool in identity.tools})
        values.update(
            {"lockfile:" + artifact.path: artifact.digest for artifact in identity.lockfiles}
        )
        return values

    old, new = entries(before), entries(after)
    changed = [
        f"{name}: before={old.get(name)!r}, after={new.get(name)!r}"
        for name in sorted(old.keys() | new.keys())
        if old.get(name) != new.get(name)
    ]
    if changed:
        raise ValidationExecutionError(
            "validation inputs changed during execution: " + "; ".join(changed)
        )


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
    nodes: _NodeObservations,
) -> ShardOutcome:
    """Execute one shard and decide whether it produced reusable evidence."""

    observed_at = datetime.now(UTC).isoformat() if shard.evidence == "world" else None
    execution = adapter.run_shard(shard)
    if execution.details:
        details[shard.name] = execution.details
    nodes.observe(shard.name, execution)
    if execution.unreached_nodes:
        raise ValidationExecutionError(
            (execution.diagnostic or f"{shard.name} reported unreached nodes")
            + f"\n{shard.name}: {len(execution.unreached_nodes)} selected nodes unreached"
        )
    if execution.failed_nodes:
        raise ValidationExecutionError(f"{shard.name} reported failed nodes")
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
class _NodeObservations:
    """First-attempt node outcomes reported by every shard that ran."""

    failed: list[NodeIdentity] = field(default_factory=list)
    recovered: list[NodeIdentity] = field(default_factory=list)
    unreached: list[NodeIdentity] = field(default_factory=list)
    executions: dict[str, ShardExecution] = field(default_factory=dict)

    def observe(self, shard: str, execution: ShardExecution) -> None:
        self.executions[shard] = execution
        self.unreached.extend(
            node
            for node in ((shard, item) for item in execution.unreached_nodes)
            if node not in self.unreached
        )
        recovered = [(shard, str(item["node_id"])) for item in execution.recovered]
        for node in [*((shard, item) for item in execution.failed_nodes), *recovered]:
            if node not in self.failed:
                self.failed.append(node)
        self.recovered.extend(node for node in recovered if node not in self.recovered)


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
    """One verdict owner for the current run; historical failures impose no debt."""
    result = _ExecutionResult()
    outcomes, names, inherited_names = result.outcomes, result.names, result.inherited
    recovered, shard_details, advisories = result.recovered, result.details, result.advisories
    reusable = reusable or {}
    nodes = _NodeObservations()
    passed: list[str] = []
    proven = executed if executed is not None else set()
    shard_by_name = {shard.name: shard for shard in graph.shards}
    today = inputs.today or datetime.now(UTC).date()
    failures: list[str] = []
    failed_shards: list[ShardFailure] = []
    validation_failed = False
    unproven: set[str] = set()
    # Infrastructure stops dependents of either kind; a failed verdict gates only requires.
    unavailable: set[str] = set()
    for name in graph.execution_order(gate):
        shard = shard_by_name[name]
        blocked = sorted(
            unproven.intersection(shard.requires) | unavailable.intersection(shard.after)
        )
        if blocked:
            unproven.add(name)
            if unavailable.intersection(blocked):
                unavailable.add(name)
            failures.append(f"{name}: skipped after {', '.join(blocked)}")
            failed_shards.append(ShardFailure(name, skipped_after=tuple(blocked)))
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
                    shard,
                    inputs,
                    adapter,
                    today=today,
                    recovered=recovered,
                    details=shard_details,
                    nodes=nodes,
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
            observed = nodes.executions.get(name)
            failed_shards.append(
                ShardFailure(name, observed.exit_code, observed.failed_checks)
                if observed is not None
                else ShardFailure(name)
            )
            if isinstance(error, ValidationInfrastructureError):
                unavailable.add(name)
            else:
                validation_failed = True
            continue
        outcomes.append(outcome)
        passed.append(name)
        if outcome.evidence == "tree":
            proven.add(shard.digest)
    if failures:
        failure_type = (
            ValidationExecutionError if validation_failed else ValidationInfrastructureError
        )
        if nodes.unreached:
            # Stated last so a truncated diagnostic still shows it.
            failures.append(f"{len(nodes.unreached)} selected nodes unreached")
        # Last, so a diagnostic truncated from the front still names every failure.
        failures.append(
            "failed shards: " + "; ".join(failure.summary() for failure in failed_shards)
        )
        raise failure_type(
            "; ".join(failures),
            failed_nodes=tuple(nodes.failed),
            recovered_nodes=tuple(nodes.recovered),
            passed_shards=tuple(passed),
            unreached_nodes=tuple(nodes.unreached),
            failed_shards=tuple(failed_shards),
        )
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
    result = _execute_shards(
        graph,
        gate,
        inputs,
        adapter,
        reusable=reusable,
    )
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
    require_unchanged_identity(identity, build_evidence_identity(graph, inputs, adapter))
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
    "ShardFailure",
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
        graph,
        gate,
        projected,
        adapter,
        executed=executed,
        advisory_world=advisory_world,
    )
    if identity is not None:
        require_unchanged_identity(identity, build_evidence_identity(graph, projected, adapter))
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
