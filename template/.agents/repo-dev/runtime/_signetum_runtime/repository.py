# Generated from signetum.validation.repository; edit the engine source and regenerate.
"""Git repository adapter and durable receipt boundary for validation v2."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 -- declarative argv, never a shell
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from . import resources as resources
from .configuration import configured_validation as _project_validation
from .evidence_receipts import (
    EvidenceReceipt,
)
from .execution import (
    ShardExecution,
    ValidationExecutionError,
    ValidationInfrastructureError,
    ValidationInputs,
    build_evidence_identity,
    execute_diagnostic_gate,
    execute_gate,
)
from .findings import Finding, FindingsError, parse_findings
from .git import GitError, git_output
from .manifest import RepositoryManifest, load_manifest
from .process import run_command
from .profiles import builtin_catalog
from .ratchet import run_ratchet
from .receipt_store import ReceiptStore
from .recovery import shard_execution
from .validation import (
    ToolDeclaration,
    ValidationGraph,
    ValidationShard,
)


class RepositoryValidationAdapter:
    """Execute a resolved graph against one clean repository worktree."""

    def __init__(self, repository: Path, *, member_base: str | None = None) -> None:
        self.repository = repository.resolve()
        self.member_base = member_base
        self.observed_tools: dict[str, str] = {}

    def _git(self, *arguments: str) -> str:
        try:
            return git_output(self.repository, *arguments)
        except GitError as error:
            raise ValidationInfrastructureError(str(error)) from error

    def require_clean(self) -> None:
        if status := self._git("status", "--porcelain"):
            raise ValidationExecutionError(f"worktree is not clean: {status}")

    def commit_identity(self) -> str:
        return self._git("rev-parse", "HEAD")

    def tree_identity(self) -> str:
        return self._git("rev-parse", "HEAD^{tree}")

    def read_file(self, path: str) -> bytes:
        candidate = (self.repository / path).resolve()
        if not candidate.is_relative_to(self.repository):
            raise ValidationExecutionError(f"file escapes repository: {path}")
        try:
            return candidate.read_bytes()
        except OSError as error:
            raise ValidationInfrastructureError(
                f"declared validation input is unavailable: {path}"
            ) from error

    def identify_tool(self, tool: ToolDeclaration) -> str:
        try:
            completed = run_command(self.repository, tool.identity_command, timeout_seconds=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValidationInfrastructureError(
                f"tool identity unavailable: {tool.name}: {error}"
            ) from error
        if completed.returncode:
            raise ValidationInfrastructureError(f"tool identity command failed: {tool.name}")
        identity = completed.stdout.strip()
        if not identity:
            raise ValidationInfrastructureError(f"tool identity is empty: {tool.name}")
        self.observed_tools[tool.name] = identity
        return identity

    def run_shard(self, shard: ValidationShard) -> ShardExecution:
        started = time.perf_counter()
        if weight_path := os.environ.get("SIGNETUM_SCHEDULE_FILE"):
            try:
                relative = Path(weight_path).resolve().relative_to(self.repository).as_posix()
            except ValueError as error:
                raise ValidationInfrastructureError(
                    "weight file must be repository-owned"
                ) from error
            if (
                relative
                not in load_manifest(self.repository / "signetum.toml").repository.lockfiles
            ):
                raise ValidationInfrastructureError(
                    "weight file must be a declared validation input"
                )
        allocation = (
            resources.allocate_workers(
                shard.workers, shard.worker_memory_mb, resources.observe_resources()
            )
            if shard.workers
            else {"workers": 0, "declared_workers": 0}
        )
        enclosing = os.environ.get("SIGNETUM_VALIDATION_WORKERS")
        if enclosing is not None or os.environ.get("PYTEST_XDIST_WORKER"):
            if enclosing is not None and not enclosing.isdecimal():
                raise ValidationInfrastructureError("invalid enclosing worker allocation")
            # Each xdist worker is one lane of its enclosing allocation.
            limit = 1 if os.environ.get("PYTEST_XDIST_WORKER") else max(1, int(enclosing or "0"))
            allocation["enclosing_worker_limit"] = limit
            allocation["workers"] = min(allocation["workers"], limit)
        if shard.ratchet_command and self.member_base is not None:
            execution = run_ratchet(
                self.repository,
                shard,
                self.member_base,
                tuple(sorted(self.observed_tools.items())),
                workers=allocation["workers"],
            )
        else:
            with tempfile.TemporaryDirectory(prefix="signetum-recovery-") as scratch:
                report = Path(scratch) / "recovered.json"
                try:
                    execution = self._run_shard(shard, report, allocation["workers"])
                except OSError as error:
                    raise ValidationInfrastructureError(
                        f"shard command unavailable: {shard.name}: {error}"
                    ) from error
        elapsed = time.perf_counter() - started
        print(
            json.dumps(
                {
                    "event": "validation.shard",
                    "shard": shard.name,
                    "elapsed_seconds": elapsed,
                    "command_succeeded": execution.succeeded,
                    "resource_allocation": allocation,
                }
            ),
            file=sys.stderr,
        )
        return replace(
            execution,
            details={
                **execution.details,
                "resource_allocation": allocation,
                "elapsed_seconds": elapsed,
            },
        )

    def _run_shard(self, shard: ValidationShard, report: Path, workers: int) -> ShardExecution:
        try:
            completed = run_command(
                self.repository,
                shard.command,
                timeout_seconds=shard.timeout_seconds,
                environment=dict(
                    os.environ,
                    SIGNETUM_RECOVERY_REPORT=str(report),
                    SIGNETUM_VALIDATION_WORKERS=str(workers),
                ),
            )
        except subprocess.TimeoutExpired:
            # A shard which never returns is otherwise indistinguishable from a
            # slow one, so the gate would wait forever and report nothing.
            return ShardExecution(
                False,
                f"{shard.name} did not return within {shard.timeout_seconds}s",
            )
        return shard_execution(shard.name, completed, report)

    def report_findings(self, shard: ValidationShard) -> tuple[Finding, ...]:
        """Run the declared findings command and read the Signetum document.

        A findings command reports through its document, not its exit status: a
        tool which exits nonzero precisely because it found something is the
        ordinary case.
        """

        try:
            completed = run_command(
                self.repository, shard.findings_command, timeout_seconds=shard.timeout_seconds
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValidationInfrastructureError(
                f"findings command unavailable: {shard.name}: {error}"
            ) from error
        try:
            return parse_findings(completed.stdout)
        except FindingsError as error:
            raise ValidationExecutionError(f"{shard.name}: {error}") from error


def run_repository_gate(
    repository: Path,
    graph: ValidationGraph,
    gate: str,
    inputs: ValidationInputs,
    receipt_root: Path,
) -> tuple[EvidenceReceipt, Path]:
    """Run one gate against a clean tree and persist its v2 receipt."""

    adapter = RepositoryValidationAdapter(repository)
    adapter.require_clean()
    adapter.member_base = inputs.base if gate == "member" else None
    receipt = execute_gate(graph, gate, inputs, adapter)
    adapter.require_clean()
    return receipt, ReceiptStore(receipt_root).write(gate, receipt)


def verify_repository_gate(
    repository: Path,
    graph: ValidationGraph,
    gate: str,
    inputs: ValidationInputs,
    receipt_root: Path,
) -> Path:
    """Re-observe every bound input and locate evidence proving this gate."""

    adapter = RepositoryValidationAdapter(repository)
    adapter.require_clean()
    expected_identity = build_evidence_identity(graph, inputs, adapter)
    order = set(graph.execution_order(gate))
    required = frozenset(shard.digest for shard in graph.shards if shard.name in order)
    return ReceiptStore(receipt_root).matching(gate, expected_identity, required)


__all__ = [
    "RepositoryValidationAdapter",
    "run_repository_gate",
    "verify_repository_gate",
]


def configured_validation(
    manifest: RepositoryManifest, *, member_shards: tuple[str, ...] | None = None
):
    return _project_validation(manifest, catalog=builtin_catalog(), member_shards=member_shards)


def run_diagnostic_gate(
    repository: Path,
    graph: ValidationGraph,
    gate: str,
    *,
    executed: set[str] | None = None,
    advisory_world: bool = False,
    member_base: str | None = None,
    tools: tuple[ToolDeclaration, ...] = (),
) -> dict[str, object]:
    """Execute checks without granting readiness or publishing delivery evidence."""
    return execute_diagnostic_gate(
        graph,
        gate,
        RepositoryValidationAdapter(repository, member_base=member_base),
        executed=executed,
        advisory_world=advisory_world,
        tools=tools,
    )
