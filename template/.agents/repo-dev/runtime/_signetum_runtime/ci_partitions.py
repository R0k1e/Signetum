# Generated from signetum.ci_partitions; edit the engine source and regenerate.
"""Optional source-bound CI partitions; aggregate diagnostics never authorize delivery."""

import fnmatch
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from .contract_values import FrozenContract
from .evidence_receipts import ArtifactIdentity, EvidenceIdentity
from .execution import ValidationExecutionError, build_evidence_identity
from .git import read_blob_contents, regular_tree_files
from .manifest import load_manifest
from .operation_cli import OperationParser, utility_failure
from .pytest_scheduling import shared_file_groups
from .repository import RepositoryValidationAdapter, configured_validation
from .repository_selection import _digest
from .selection_contracts import repository_file
from .serialization import contract_mapping, dataclass_from_mapping, load_json
from .test_scheduling import partition_units
from .validation import ValidationGraph


@dataclass(frozen=True, kw_only=True)
class PartitionConfiguration(FrozenContract):
    schema_version: Literal[1]
    shard: str
    roots: tuple[str, ...]
    patterns: tuple[str, ...]
    argument_index: int
    slices: int
    weights: dict[str, float] = field(default_factory=dict)
    framework: Literal["files", "pytest"] = "files"
    groups: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.roots or not self.patterns or self.argument_index < 1:
            raise ValueError("partitions require explicit roots, patterns and command-tail binding")
        for root in self.roots:
            repository_file(root)


@dataclass(frozen=True, kw_only=True)
class PartitionPlan(FrozenContract):
    schema_version: Literal[1]
    run_id: str
    identity: EvidenceIdentity
    configuration: ArtifactIdentity
    shard: str
    command: tuple[str, ...]
    argument_index: int
    partitions: tuple[tuple[str, ...], ...]

    @property
    def digest(self) -> str:
        return _digest(contract_mapping(self))


@dataclass(frozen=True, kw_only=True)
class PartitionResult(FrozenContract):
    schema_version: Literal[1]
    plan_digest: str
    identity: EvidenceIdentity
    index: int
    files: tuple[str, ...]
    command: tuple[str, ...]
    passed: bool
    recovered: bool


def _partition_paths(config: PartitionConfiguration, paths: tuple[str, ...]) -> tuple[str, ...]:
    files = tuple(
        sorted(
            p
            for p in paths
            if any(root == "." or p.startswith(root.rstrip("/") + "/") for root in config.roots)
            and any(fnmatch.fnmatchcase(p, pattern) for pattern in config.patterns)
        )
    )
    if any(p.startswith("-") or "::" in p for p in files):
        raise ValueError("partition file cannot masquerade as an option or node")
    return files


def partition_snapshot(
    config: PartitionConfiguration,
    graph: ValidationGraph,
    sources: Mapping[str, bytes],
    *,
    configuration_path: str,
    declared_inputs: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    """Plan immutable supplied source bytes; the repository adapter owns acquisition."""
    if configuration_path not in declared_inputs:
        raise ValueError("partition configuration must be a declared validation input")
    shard = next((s for s in graph.shards if s.name == config.shard), None)
    if shard is None or shard.ratchet_command or shard.evidence != "tree":
        raise ValueError("partitioning requires a declared non-ratchet tree shard")
    if config.shard not in graph.execution_order("final") or config.argument_index > len(
        shard.command
    ):
        raise ValueError("partition shard must be final-covered and its command binding valid")
    files = _partition_paths(config, tuple(sources))
    groups = config.groups
    if config.framework == "pytest":
        groups = (*groups, *shared_file_groups({p: sources[p] for p in files}))
    return partition_units(files, config.slices, config.weights, groups)


def create_plan(
    repository: Path, configuration_path: Path, *, run_id: str | None = None
) -> PartitionPlan:
    adapter = RepositoryValidationAdapter(repository)
    adapter.require_clean()
    relative = configuration_path.resolve().relative_to(repository.resolve()).as_posix()
    repository_file(relative)
    config = dataclass_from_mapping(
        PartitionConfiguration, load_json(configuration_path.read_text()), use_defaults=True
    )
    manifest = load_manifest(repository / "signetum.toml")
    graph, inputs = configured_validation(manifest)
    inventory = regular_tree_files(repository, adapter.commit_identity())
    files = _partition_paths(config, tuple(inventory))
    blobs = read_blob_contents(repository, tuple(sorted({inventory[p] for p in files})))
    partitions = partition_snapshot(
        config,
        graph,
        {p: blobs[inventory[p]] for p in files},
        configuration_path=relative,
        declared_inputs=manifest.repository.lockfiles,
    )
    shard = next(s for s in graph.shards if s.name == config.shard)
    identity = build_evidence_identity(graph, inputs, adapter)
    if identity.commit != adapter.commit_identity() or identity.tree != adapter.tree_identity():
        raise ValueError("source changed while planning partitions")
    return PartitionPlan(
        schema_version=1,
        run_id=run_id or uuid.uuid4().hex,
        identity=identity,
        configuration=ArtifactIdentity.from_bytes(relative, configuration_path.read_bytes()),
        shard=config.shard,
        command=shard.command,
        argument_index=config.argument_index,
        partitions=partitions,
    )


def verify_plan(repository: Path, plan: PartitionPlan) -> None:
    if create_plan(repository, repository / plan.configuration.path, run_id=plan.run_id) != plan:
        raise ValueError("CI plan no longer matches current source, tools or partition rules")


def run_partition(repository: Path, plan: PartitionPlan, index: int) -> PartitionResult:
    verify_plan(repository, plan)
    if type(index) is not int or not 0 <= index < len(plan.partitions):
        raise ValueError("partition index is outside the plan")
    manifest = load_manifest(repository / "signetum.toml")
    graph, _ = configured_validation(manifest)
    shard = next(s for s in graph.shards if s.name == plan.shard)
    command = (*plan.command[: plan.argument_index], *plan.partitions[index])
    adapter = RepositoryValidationAdapter(repository)
    # Environment/build preparation remains the outer job's explicit owner.
    execution = adapter.run_shard(replace(shard, command=command))
    recovered = bool(execution.recovered)
    verify_plan(repository, plan)
    return PartitionResult(
        schema_version=1,
        plan_digest=plan.digest,
        identity=plan.identity,
        index=index,
        files=plan.partitions[index],
        command=command,
        passed=execution.succeeded,
        recovered=recovered,
    )


def combine(
    plan: PartitionPlan, results: tuple[PartitionResult, ...], *, job_statuses: tuple[str, ...] = ()
) -> dict[str, object]:
    if len(job_statuses) != len(plan.partitions) or any(
        status != "success" for status in job_statuses
    ):
        raise ValueError("current CI jobs are missing, failed, cancelled or skipped")
    flattened = [p for group in plan.partitions for p in group]
    if (
        not plan.partitions
        or any(not group for group in plan.partitions)
        or len(flattened) != len(set(flattened))
    ):
        raise ValueError("partition plan has empty or overlapping file coverage")
    if len(results) != len(plan.partitions) or {r.index for r in results} != set(
        range(len(plan.partitions))
    ):
        raise ValueError("partition results are missing or duplicated")
    for result in results:
        if (
            result.identity != plan.identity
            or result.plan_digest != plan.digest
            or not result.passed
            or result.recovered
            or result.files != plan.partitions[result.index]
            or result.command != (*plan.command[: plan.argument_index], *result.files)
        ):
            raise ValueError("partition evidence is failed, recovered or mismatched")
    return {
        "schema_version": 1,
        "status": "passed",
        "plan_digest": plan.digest,
        "partitions": len(results),
        "files": len(flattened),
        "source": plan.identity.commit,
        "authority": "ci_diagnostic_only",
        "next": "Complete the final gate and review before separately authorized delivery.",
    }


def main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(description=__doc__)
    parser.add_argument("operation", choices=["plan", "run", "combine"])
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--index", type=int)
    parser.add_argument("--result", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--job-status",
        action="append",
        choices=["success", "failure", "cancelled", "skipped"],
        default=[],
    )
    try:
        options = parser.parse_args(arguments)
        if options.output and options.output.exists():
            raise ValueError("result output already exists; use a fresh artifact path")
        if options.operation != "combine" and options.job_status:
            raise ValueError("only combine accepts CI job conclusions")
        if options.operation == "plan":
            if (
                options.config is None
                or options.plan
                or options.index is not None
                or options.result
            ):
                raise ValueError("plan requires only --config and optional --output")
            plan = create_plan(options.repository, options.config)
            document = contract_mapping(plan)
            result = {
                "schema_version": 1,
                "status": "planned",
                "plan_digest": plan.digest,
                "partitions": len(plan.partitions),
                "files": sum(map(len, plan.partitions)),
                "matrix": [
                    {"index": n, "files": list(files)} for n, files in enumerate(plan.partitions)
                ],
            }
        else:
            if options.plan is None or options.config:
                raise ValueError("run and combine require --plan")
            plan = dataclass_from_mapping(PartitionPlan, load_json(options.plan.read_text()))
            if options.operation == "run":
                if options.index is None or options.result:
                    raise ValueError("run requires --index without input results")
                execution = run_partition(options.repository, plan, options.index)
                document = contract_mapping(execution)
                result = {
                    **document,
                    "status": "passed"
                    if execution.passed and not execution.recovered
                    else "failed",
                }
            else:
                if options.index is not None:
                    raise ValueError("combine does not accept a partition index")
                verify_plan(options.repository, plan)
                results = tuple(
                    dataclass_from_mapping(PartitionResult, load_json(p.read_text()))
                    for p in options.result
                )
                result = combine(plan, results, job_statuses=tuple(options.job_status))
                document = result
        if options.output:
            with options.output.open("x", encoding="utf-8") as output:
                json.dump(document, output, sort_keys=True)
        if result["status"] == "failed":
            return utility_failure(
                "partition",
                ValidationExecutionError(
                    "partition command failed or retained an original failure"
                ),
                state_change="result_artifact_written" if options.output else "none",
                **document,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError) as error:
        return utility_failure("partition", error)
