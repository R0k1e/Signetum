from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from reposeal.validation import (
    GateDeclaration,
    GraphContribution,
    ToolDeclaration,
    ValidationShard,
    resolve_validation_graph,
)
from reposeal.validation.execution import (
    ValidationExecutionError,
    ValidationInputs,
    execute_gate,
)


@dataclass
class Adapter:
    failed: str | None = None
    executed: list[str] = field(default_factory=list)

    def commit_identity(self) -> str:
        return "a" * 40

    def tree_identity(self) -> str:
        return "b" * 40

    def read_file(self, path: str) -> bytes:
        return {"reposeal.toml": b"schema_version = 2\n", "uv.lock": b"lock"}[path]

    def identify_tool(self, tool: ToolDeclaration) -> str:
        return "uv 0.8.14"

    def run_shard(self, shard: ValidationShard) -> bool:
        self.executed.append(shard.name)
        return shard.name != self.failed


def _graph():
    return resolve_validation_graph(
        (
            GraphContribution(
                "core",
                shards=(
                    ValidationShard("core:static", ("check",)),
                    ValidationShard("repository:test", ("test",), ("core:static",)),
                ),
                gates=(GateDeclaration("final", ("repository:test",)),),
            ),
        )
    )


def _inputs() -> ValidationInputs:
    return ValidationInputs(
        configuration_path="reposeal.toml",
        profiles=("python-default@2",),
        lockfiles=("uv.lock",),
        tools=(ToolDeclaration("uv", ("uv", "--version")),),
    )


def test_gate_executes_dependencies_and_binds_every_declared_input() -> None:
    adapter = Adapter()

    receipt = execute_gate(_graph(), "final", _inputs(), adapter)

    assert adapter.executed == ["core:static", "repository:test"]
    assert receipt.executed_shards == ("core:static", "repository:test")
    assert receipt.identity.configuration.path == "reposeal.toml"
    assert tuple(lock.path for lock in receipt.identity.lockfiles) == ("uv.lock",)
    assert receipt.identity.tools[0].identity == "uv 0.8.14"


def test_failed_shard_produces_no_gate_evidence() -> None:
    adapter = Adapter(failed="repository:test")

    with pytest.raises(ValidationExecutionError, match="repository:test"):
        execute_gate(_graph(), "final", _inputs(), adapter)


@pytest.mark.parametrize(
    "inputs",
    [
        lambda: ValidationInputs("other.toml", (), (), ()),
        lambda: ValidationInputs("reposeal.toml", ("z@1", "a@1"), (), ()),
        lambda: ValidationInputs("reposeal.toml", (), ("z.lock", "a.lock"), ()),
        lambda: ValidationInputs(
            "reposeal.toml",
            (),
            (),
            (
                ToolDeclaration("tool", ("one",)),
                ToolDeclaration("tool", ("two",)),
            ),
        ),
    ],
)
def test_validation_inputs_fail_closed(inputs: Callable[[], object]) -> None:
    with pytest.raises(ValidationExecutionError):
        inputs()
