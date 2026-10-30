"""Versioned declarations and wire values for repository-owned test selection."""

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, Literal

from signetum.contract_values import FrozenContract
from signetum.decision_clauses import Text
from signetum.serialization import Constraints
from signetum.validation import ToolDeclaration


def repository_file(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
        or "\0" in value
    ):
        raise ValueError("selection input must name an exact repository-relative path")


@dataclass(frozen=True, kw_only=True)
class TargetBinding(FrozenContract):
    shard: Text
    roots: Annotated[tuple[Text, ...], Constraints(min_length=1)]
    argument_index: Annotated[int, Constraints(minimum=1)]

    def __post_init__(self) -> None:
        super().__post_init__()
        for root in self.roots:
            repository_file(root)


@dataclass(frozen=True, kw_only=True)
class SelectionProvider(FrozenContract):
    protocol: Literal["signetum.selection@1"]
    entrypoint: Text
    command: Annotated[tuple[Text, ...], Constraints(min_length=1)]
    tools: Annotated[tuple[ToolDeclaration, ...], Constraints(min_length=1)]
    inputs: tuple[Text, ...] = ()
    targets: tuple[TargetBinding, ...] = ()
    timeout_seconds: Annotated[int, Constraints(minimum=1)] = 60

    def __post_init__(self) -> None:
        super().__post_init__()
        for path in (self.entrypoint, *self.inputs):
            repository_file(path)
        if self.command.count("{selector}") != 1:
            raise ValueError("selection command must contain exactly one {selector} argument")
        if len({tool.name for tool in self.tools}) != len(self.tools):
            raise ValueError("selection tool identities must be unique")
        if len({target.shard for target in self.targets}) != len(self.targets):
            raise ValueError("selection target bindings must be unique per shard")
        if len(set(self.inputs)) != len(self.inputs):
            raise ValueError("selection inputs must be unique")


@dataclass(frozen=True, kw_only=True)
class PathCoverage(FrozenContract):
    path: Text
    status: Literal["covered", "unexplained"]
    shards: tuple[Text, ...]
    reason: Text


@dataclass(frozen=True, kw_only=True)
class TestTarget(FrozenContract):
    path: Text
    argument: Text


@dataclass(frozen=True, kw_only=True)
class ShardTargets(FrozenContract):
    shard: Text
    tests: Annotated[tuple[TestTarget, ...], Constraints(min_length=1)]


@dataclass(frozen=True, kw_only=True)
class SelectionResponse(FrozenContract):
    protocol: Literal["signetum.selection@1"]
    request_digest: Annotated[str, Constraints(pattern="^sha256:[0-9a-f]{64}$")]
    coverage: tuple[PathCoverage, ...]
    targets: tuple[ShardTargets, ...] = ()
