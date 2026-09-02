"""Git repository adapter and durable receipt boundary for validation v2."""

from __future__ import annotations

import hashlib
import subprocess  # nosec B404 -- declarative argv, never a shell
from pathlib import Path
from shutil import which

from reposeal.evidence.receipts import (
    EvidenceIdentity,
    EvidenceReceipt,
    ReceiptError,
    verify_gate_evidence,
)
from reposeal.findings import Finding, FindingsError, parse_findings
from reposeal.validation import ToolDeclaration, ValidationGraph, ValidationShard
from reposeal.validation.execution import (
    ShardExecution,
    ValidationExecutionError,
    ValidationInputs,
    build_evidence_identity,
    execute_gate,
)


class RepositoryValidationAdapter:
    """Execute a resolved graph against one clean repository worktree."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()

    def _git(self, *arguments: str) -> str:
        executable = which("git")
        if executable is None:
            raise ValidationExecutionError("git executable is unavailable")
        completed = subprocess.run(  # nosec B603
            (executable, "-C", str(self.repository), *arguments),
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            diagnostic = completed.stderr.strip() or completed.stdout.strip()
            raise ValidationExecutionError(diagnostic or "git identity query failed")
        return completed.stdout.strip()

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
            raise ValidationExecutionError(
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
            raise ValidationExecutionError(f"tool identity command failed: {tool.name}")
        identity = completed.stdout.strip()
        if not identity:
            raise ValidationExecutionError(f"tool identity is empty: {tool.name}")
        return identity

    def run_shard(self, shard: ValidationShard) -> ShardExecution:
        completed = subprocess.run(  # nosec B603
            shard.command,
            cwd=self.repository,
            check=False,
        )
        if completed.returncode == 0:
            return ShardExecution(True)
        return ShardExecution(False, f"{shard.name} exited {completed.returncode}")

    def report_findings(self, shard: ValidationShard) -> tuple[Finding, ...]:
        """Run the declared findings command and read the RepoSeal document.

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
