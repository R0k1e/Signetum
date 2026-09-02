"""Language-neutral named validation graph contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class ValidationGraphError(ValueError):
    """Validation declarations cannot form one deterministic graph."""


_NAME = re.compile(r"[a-z][a-z0-9_.@-]*(?::[a-z][a-z0-9_.@-]*)+")
_GATE = re.compile(r"[a-z][a-z0-9_.-]*")


def _tuple_of_strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValidationGraphError(f"{field} must be a string array")
    result = tuple(value)
    if not all(isinstance(item, str) and item for item in result):
        raise ValidationGraphError(f"{field} must contain non-empty strings")
    return result


EVIDENCE_CLASSES = ("tree", "world")


def command_digest(command: Sequence[str]) -> str:
    """Identify one exact argv independently of the shard name carrying it."""

    encoded = json.dumps(list(command), separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ValidationShard:
    """One independently executable, namespaced unit of validation."""

    name: str
    command: tuple[str, ...]
    requires: tuple[str, ...] = ()
    evidence: str = "tree"
    findings_command: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if _NAME.fullmatch(self.name) is None:
            raise ValidationGraphError(f"shard name must be namespaced: {self.name}")
        if not self.command or any(not argument for argument in self.command):
            raise ValidationGraphError(f"shard command must be non-empty: {self.name}")
        if len(self.requires) != len(set(self.requires)):
            raise ValidationGraphError(f"duplicate shard dependency: {self.name}")
        if self.evidence not in EVIDENCE_CLASSES:
            raise ValidationGraphError(f"unsupported evidence class: {self.name}")
        if self.findings_command and self.evidence != "world":
            raise ValidationGraphError(f"only a world shard reports findings: {self.name}")
        if self.findings_command and any(not argument for argument in self.findings_command):
            raise ValidationGraphError(f"findings command must be non-empty: {self.name}")

    @property
    def digest(self) -> str:
        """Return the exact command identity proven by executing this shard."""

        return command_digest(self.command)


@dataclass(frozen=True)
class GateDeclaration:
    """One contribution to a public named gate."""

    name: str
    shards: tuple[str, ...]

    def __post_init__(self) -> None:
        if _GATE.fullmatch(self.name) is None:
            raise ValidationGraphError(f"invalid gate name: {self.name}")
        if len(self.shards) != len(set(self.shards)):
            raise ValidationGraphError(f"duplicate shard in gate: {self.name}")


@dataclass(frozen=True)
class GraphContribution:
    """Core, one profile, or the repository's graph additions."""

    identity: str
    shards: tuple[ValidationShard, ...] = ()
    gates: tuple[GateDeclaration, ...] = ()

    def __post_init__(self) -> None:
        if not self.identity:
            raise ValidationGraphError("graph contribution identity must be non-empty")


@dataclass(frozen=True)
class ToolDeclaration:
    """One tool whose exact identity is captured before executing a graph."""

    name: str
    identity_command: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.identity_command:
            raise ValidationGraphError("tool name and identity command must be non-empty")


@dataclass(frozen=True)
class ValidationConfiguration:
    """Manifest-independent adapter projection for validation configuration."""

    contribution: GraphContribution
    tools: tuple[ToolDeclaration, ...] = ()

    @classmethod
    def from_mapping(cls, identity: str, document: Mapping[str, object]) -> ValidationConfiguration:
        """Validate an ordinary mapping supplied by Core or a profile loader."""

        raw_shards = document.get("shards", ())
        raw_gates = document.get("gates", ())
        raw_tools = document.get("tools", ())
        if not isinstance(raw_shards, Sequence) or isinstance(raw_shards, str):
            raise ValidationGraphError("shards must be an object array")
        if not isinstance(raw_gates, Sequence) or isinstance(raw_gates, str):
            raise ValidationGraphError("gates must be an object array")
        if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, str):
            raise ValidationGraphError("tools must be an object array")

        shards: list[ValidationShard] = []
        for raw in raw_shards:
            if not isinstance(raw, Mapping):
                raise ValidationGraphError("shards must be an object array")
            name = raw.get("name")
            if not isinstance(name, str):
                raise ValidationGraphError("shard.name must be a string")
            evidence = raw.get("evidence", "tree")
            if not isinstance(evidence, str):
                raise ValidationGraphError("shard.evidence must be a string")
            shards.append(
                ValidationShard(
                    name,
                    _tuple_of_strings(raw.get("command"), "shard.command"),
                    _tuple_of_strings(raw.get("requires", ()), "shard.requires"),
                    evidence,
                    _tuple_of_strings(raw.get("findings_command", ()), "shard.findings_command"),
                )
            )

        gates: list[GateDeclaration] = []
        for raw in raw_gates:
            if not isinstance(raw, Mapping):
                raise ValidationGraphError("gates must be an object array")
            name = raw.get("name")
            if not isinstance(name, str):
                raise ValidationGraphError("gate.name must be a string")
            gates.append(GateDeclaration(name, _tuple_of_strings(raw.get("shards"), "gate.shards")))

        tools: list[ToolDeclaration] = []
        for raw in raw_tools:
            if not isinstance(raw, Mapping):
                raise ValidationGraphError("tools must be an object array")
            name = raw.get("name")
            if not isinstance(name, str):
                raise ValidationGraphError("tool.name must be a string")
            tools.append(
                ToolDeclaration(
                    name,
                    _tuple_of_strings(raw.get("identity_command"), "tool.identity_command"),
                )
            )
        if len(tools) != len({tool.name for tool in tools}):
            raise ValidationGraphError(f"duplicate tool owner in contribution: {identity}")
        return cls(GraphContribution(identity, tuple(shards), tuple(gates)), tuple(tools))


@dataclass(frozen=True)
class ResolvedGate:
    """One gate after all contributions have been unioned."""

    name: str
    shards: tuple[str, ...]


@dataclass(frozen=True)
class ValidationGraph:
    """One canonical validation graph used by execution and evidence."""

    shards: tuple[ValidationShard, ...]
    gates: tuple[ResolvedGate, ...]
    digest: str

    def gate(self, name: str) -> ResolvedGate:
        for gate in self.gates:
            if gate.name == name:
                return gate
        raise ValidationGraphError(f"unknown gate: {name}")

    def execution_order(self, gate: str) -> tuple[str, ...]:
        selected = self.gate(gate)
        shards = {shard.name: shard for shard in self.shards}
        ordered: list[str] = []
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in ordered:
                return
            if name in visiting:
                raise ValidationGraphError(f"cyclic shard dependency: {name}")
            shard = shards.get(name)
            if shard is None:
                raise ValidationGraphError(f"unknown shard: {name}")
            visiting.add(name)
            for dependency in sorted(shard.requires):
                visit(dependency)
            visiting.remove(name)
            ordered.append(name)

        for name in selected.shards:
            visit(name)
        return tuple(ordered)


def resolve_validation_graph(
    contributions: Sequence[GraphContribution],
) -> ValidationGraph:
    """Compose declarations by union while rejecting ambiguous ownership."""

    shard_owners: dict[str, str] = {}
    shards: dict[str, ValidationShard] = {}
    gate_shards: dict[str, set[str]] = {}
    for contribution in contributions:
        for shard in contribution.shards:
            owner = shard_owners.get(shard.name)
            if owner is not None:
                raise ValidationGraphError(
                    f"duplicate shard owner: {shard.name} ({owner}, {contribution.identity})"
                )
            shard_owners[shard.name] = contribution.identity
            shards[shard.name] = shard
        for gate in contribution.gates:
            gate_shards.setdefault(gate.name, set()).update(gate.shards)

    resolved_shards = tuple(shards[name] for name in sorted(shards))
    resolved_gates = tuple(
        ResolvedGate(name, tuple(sorted(gate_shards[name]))) for name in sorted(gate_shards)
    )
    graph_document = {
        "gates": [{"name": gate.name, "shards": gate.shards} for gate in resolved_gates],
        "shards": [
            {
                "command": shard.command,
                "evidence": shard.evidence,
                "findings_command": shard.findings_command,
                "name": shard.name,
                "requires": tuple(sorted(shard.requires)),
            }
            for shard in resolved_shards
        ],
    }
    encoded = json.dumps(graph_document, sort_keys=True, separators=(",", ":")).encode()
    graph = ValidationGraph(
        resolved_shards,
        resolved_gates,
        "sha256:" + hashlib.sha256(encoded).hexdigest(),
    )
    for gate in resolved_gates:
        order = graph.execution_order(gate.name)
        if gate.name != "member":
            continue
        world = tuple(name for name in order if shards[name].evidence == "world")
        if world:
            raise ValidationGraphError(
                "member closure cannot depend on world state: " + ", ".join(sorted(world))
            )
    return graph


def resolve_tools(configurations: Sequence[ValidationConfiguration]) -> tuple[ToolDeclaration, ...]:
    """Union tool declarations while retaining exactly one owner per name."""

    owners: dict[str, str] = {}
    tools: dict[str, ToolDeclaration] = {}
    for configuration in configurations:
        for tool in configuration.tools:
            owner = owners.get(tool.name)
            if owner is not None:
                new_owner = configuration.contribution.identity
                raise ValidationGraphError(
                    f"duplicate tool owner: {tool.name} ({owner}, {new_owner})"
                )
            owners[tool.name] = configuration.contribution.identity
            tools[tool.name] = tool
    return tuple(tools[name] for name in sorted(tools))


__all__ = [
    "EVIDENCE_CLASSES",
    "GateDeclaration",
    "GraphContribution",
    "ResolvedGate",
    "ToolDeclaration",
    "ValidationConfiguration",
    "ValidationGraph",
    "ValidationGraphError",
    "ValidationShard",
    "command_digest",
    "resolve_tools",
    "resolve_validation_graph",
]
