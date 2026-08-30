"""Execution adapter for exact validation identities and shard commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from reposeal.evidence.receipts import (
    ArtifactIdentity,
    EvidenceIdentity,
    EvidenceReceipt,
    ToolIdentity,
    combine_shard_evidence,
)
from reposeal.validation import ToolDeclaration, ValidationGraph, ValidationShard


class ValidationExecutionError(ValueError):
    """A declared tool or shard could not produce successful evidence."""


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

    def run_shard(self, shard: ValidationShard) -> bool:
        """Execute one shard command and return its success verdict."""


@dataclass(frozen=True)
class ValidationInputs:
    """Explicit Core projection used to build one evidence identity."""

    configuration_path: str
    profiles: tuple[str, ...]
    lockfiles: tuple[str, ...]
    tools: tuple[ToolDeclaration, ...]

    def __post_init__(self) -> None:
        if self.configuration_path != "reposeal.toml":
            raise ValidationExecutionError("configuration path must be reposeal.toml")
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
        configuration=configuration,
        profiles=inputs.profiles,
        graph=graph.digest,
        lockfiles=lockfiles,
        tools=tools,
    )


def execute_gate(
    graph: ValidationGraph,
    gate: str,
    inputs: ValidationInputs,
    adapter: ValidationAdapter,
) -> EvidenceReceipt:
    """Execute one resolved gate and compose only its successful shard evidence."""

    identity = build_evidence_identity(graph, inputs, adapter)
    shard_by_name = {shard.name: shard for shard in graph.shards}
    receipts: list[EvidenceReceipt] = []
    for name in graph.execution_order(gate):
        if not adapter.run_shard(shard_by_name[name]):
            raise ValidationExecutionError(f"validation shard failed: {name}")
        receipts.append(EvidenceReceipt.shard(identity=identity, shard=name))
    return combine_shard_evidence(
        gate=gate,
        required_shards=graph.execution_order(gate),
        receipts=tuple(receipts),
    )


__all__ = [
    "ValidationAdapter",
    "ValidationExecutionError",
    "ValidationInputs",
    "build_evidence_identity",
    "execute_gate",
]
