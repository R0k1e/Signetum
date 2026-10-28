"""Git repository adapter and durable receipt boundary for validation v2."""

from __future__ import annotations

import hashlib
import subprocess  # nosec B404 -- declarative argv, never a shell
import sys
from pathlib import Path

from signetum.evidence.receipts import (
    EvidenceIdentity,
    EvidenceReceipt,
    ReceiptError,
    verify_gate_evidence,
)
from signetum.findings import Finding, FindingsError, parse_findings
from signetum.git import GitError, git_output
from signetum.manifest import RepositoryManifest
from signetum.profiles import resolve_profiles
from signetum.validation import (
    GateDeclaration,
    GraphContribution,
    ToolDeclaration,
    ValidationGraph,
    ValidationShard,
    resolve_validation_graph,
)
from signetum.validation.execution import (
    ShardExecution,
    ValidationExecutionError,
    ValidationInfrastructureError,
    ValidationInputs,
    build_evidence_identity,
    execute_gate,
)


class RepositoryValidationAdapter:
    """Execute a resolved graph against one clean repository worktree."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()

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
        completed = subprocess.run(  # nosec B603
            tool.identity_command,
            cwd=self.repository,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise ValidationInfrastructureError(f"tool identity command failed: {tool.name}")
        identity = completed.stdout.strip()
        if not identity:
            raise ValidationInfrastructureError(f"tool identity is empty: {tool.name}")
        return identity

    def run_shard(self, shard: ValidationShard) -> ShardExecution:
        try:
            completed = subprocess.run(  # nosec B603
                shard.command,
                cwd=self.repository,
                check=False,
                timeout=shard.timeout_seconds,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            # A shard which never returns is otherwise indistinguishable from a
            # slow one, so the gate would wait forever and report nothing.
            return ShardExecution(
                False,
                f"{shard.name} did not return within {shard.timeout_seconds}s",
            )
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        if completed.returncode == 0:
            return ShardExecution(True)
        diagnostic = completed.stdout + completed.stderr
        return ShardExecution(False, f"{shard.name} exited {completed.returncode}\n{diagnostic}")

    def report_findings(self, shard: ValidationShard) -> tuple[Finding, ...]:
        """Run the declared findings command and read the Signetum document.

        A findings command reports through its document, not its exit status: a
        tool which exits nonzero precisely because it found something is the
        ordinary case.
        """

        completed = subprocess.run(  # nosec B603
            shard.findings_command,
            cwd=self.repository,
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            return parse_findings(completed.stdout)
        except FindingsError as error:
            raise ValidationExecutionError(f"{shard.name}: {error}") from error


class ReceiptStore:
    """Content-addressed successful evidence outside the repository tree."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def write(self, gate: str, receipt: EvidenceReceipt) -> Path:
        encoded = receipt.to_json()
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / f"{gate}-{digest}.json"
        destination.write_text(encoded, encoding="utf-8")
        return destination

    def matching(
        self,
        gate: str,
        identity: EvidenceIdentity,
        required_digests: frozenset[str],
    ) -> Path:
        """Locate evidence binding this identity and proving these commands.

        Evidence is never matched by whole-document equality. A world shard
        records when it observed the world, so two honest runs of one gate are
        never byte-identical.
        """

        for path in sorted(self.root.glob(f"{gate}-*.json")):
            try:
                observed = EvidenceReceipt.from_json(path.read_text(encoding="utf-8"))
                verify_gate_evidence(observed, expected_identity=identity, gate=gate)
            except (OSError, ReceiptError):
                continue
            if required_digests <= observed.execution.command_digests:
                return path
        raise ReceiptError(f"no {gate} receipt proves the required commands")


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
    receipt = execute_gate(graph, gate, inputs, adapter)
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
    "ReceiptStore",
    "RepositoryValidationAdapter",
    "run_repository_gate",
    "verify_repository_gate",
]


def configured_validation(
    manifest: RepositoryManifest, *, member_shards: tuple[str, ...] | None = None
):
    resolved = resolve_profiles(
        manifest.profiles.enabled, replacements=manifest.profiles.replacements
    )
    shards = [
        ValidationShard(
            item.name,
            item.command,
            item.requires,
            item.evidence,
            item.findings_command,
            item.timeout_seconds,
        )
        for item in manifest.validation.shards
    ]
    gates = [GateDeclaration(item.name, item.shards) for item in manifest.validation.gates]
    if member_shards is not None:
        gates = [item for item in gates if item.name != "member"]
        gates.append(GateDeclaration("member", member_shards))
    graph = resolve_validation_graph(
        (GraphContribution("repository", tuple(shards), tuple(gates)),)
    )
    inputs = ValidationInputs(
        "signetum.toml",
        tuple(sorted(profile.identity for profile in resolved)),
        tuple(sorted(manifest.repository.lockfiles)),
        tuple(
            ToolDeclaration(item.name, item.identity_command) for item in manifest.validation.tools
        ),
    )
    return graph, inputs


def run_diagnostic_gate(
    repository: Path,
    graph: ValidationGraph,
    gate: str,
    *,
    executed: set[str] | None = None,
    advisory_world: bool = False,
) -> dict[str, object]:
    """Execute checks without granting readiness or publishing delivery evidence."""
    proven = executed if executed is not None else set()
    by_name = {shard.name: shard for shard in graph.shards}
    names: list[str] = []
    advisories: list[dict[str, str]] = []
    adapter = RepositoryValidationAdapter(repository)
    for name in graph.execution_order(gate):
        shard = by_name[name]
        if shard.evidence == "tree" and shard.digest in proven:
            continue
        result = adapter.run_shard(shard)
        names.append(name)
        if not result.succeeded:
            if shard.evidence == "world" and advisory_world:
                advisories.append({"shard": name, "diagnostic": result.diagnostic})
                continue
            raise ValidationExecutionError(result.diagnostic or f"check failed: {name}")
        if shard.evidence == "tree":
            proven.add(shard.digest)
    return {"executed": names, "advisories": advisories}
