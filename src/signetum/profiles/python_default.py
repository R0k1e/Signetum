"""Declarative validation projection for the maintained Python default profile."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from tomllib import loads
from typing import NotRequired, TypedDict, cast

from signetum.resources import profiles as profile_resources

_RESOURCE = "python-default-v1.toml"
_PATH_ARGUMENTS = {
    "{source}": "source",
    "{unit}": "unit",
    "{integration}": "integration",
}


class ToolMapping(TypedDict):
    name: str
    identity_command: list[str]


class ShardMapping(TypedDict):
    name: str
    command: list[str]
    evidence: NotRequired[str]
    findings_command: NotRequired[list[str]]


class GateMapping(TypedDict):
    name: str
    shards: list[str]


class PythonDefaultValidation(TypedDict):
    identity: str
    tools: list[ToolMapping]
    shards: list[ShardMapping]
    gates: list[GateMapping]


class _ProfileDocument(TypedDict):
    identity: str
    tools: list[ToolMapping]
    shards: list[ShardMapping]
    gates: list[GateMapping]


@dataclass(frozen=True)
class PythonDefaultPaths:
    """Repository-owned locations consumed by Python validation shards."""

    source: tuple[str, ...] = ("src",)
    unit: tuple[str, ...] = ("tests/unit",)
    integration: tuple[str, ...] = ("tests/integration",)

    def __post_init__(self) -> None:
        for name in ("source", "unit", "integration"):
            values = getattr(self, name)
            if not values or any(not value for value in values):
                raise ValueError(f"Python {name} paths must be non-empty")


def _expand(command: list[str], paths: PythonDefaultPaths) -> list[str]:
    expanded: list[str] = []
    for argument in command:
        field = _PATH_ARGUMENTS.get(argument)
        if field is None:
            expanded.append(argument)
        else:
            expanded.extend(getattr(paths, field))
    return expanded


def python_default_validation(
    paths: PythonDefaultPaths | None = None,
) -> PythonDefaultValidation:
    """Return the profile's ValidationConfiguration-compatible mapping."""

    configured_paths = paths or PythonDefaultPaths()
    resource = files(profile_resources) / _RESOURCE
    document = cast(_ProfileDocument, loads(resource.read_text(encoding="utf-8")))
    shards: list[ShardMapping] = []
    for shard in document["shards"]:
        mapping = ShardMapping(
            name=shard["name"],
            command=_expand(shard["command"], configured_paths),
        )
        if "evidence" in shard:
            mapping["evidence"] = shard["evidence"]
        if "findings_command" in shard:
            mapping["findings_command"] = _expand(shard["findings_command"], configured_paths)
        shards.append(mapping)
    return PythonDefaultValidation(
        identity=document["identity"],
        tools=document["tools"],
        shards=shards,
        gates=document["gates"],
    )


__all__ = ["PythonDefaultPaths", "PythonDefaultValidation", "python_default_validation"]
