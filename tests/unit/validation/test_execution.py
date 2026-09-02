from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import pytest

from signetum.findings import Finding, FindingsError, parse_findings
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
    ValidationInputs,
    execute_gate,
)
from signetum.waivers import Waiver


@dataclass
class Adapter:
    failed: str | None = None
    executed: list[str] = field(default_factory=list)
    document: str = ""

    def commit_identity(self) -> str:
        return "a" * 40

    def tree_identity(self) -> str:
        return "b" * 40

    def read_file(self, path: str) -> bytes:
        return {"signetum.toml": b"schema_version = 2\n", "uv.lock": b"lock"}[path]

    def identify_tool(self, tool: ToolDeclaration) -> str:
        return "uv 0.8.14"

    def run_shard(self, shard: ValidationShard) -> ShardExecution:
        self.executed.append(shard.name)
        return ShardExecution(shard.name != self.failed)

    def report_findings(self, shard: ValidationShard) -> tuple[Finding, ...]:
        try:
            return parse_findings(self.document)
        except FindingsError as error:
            raise ValidationExecutionError(f"{shard.name}: {error}") from error


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
        configuration_path="signetum.toml",
        profiles=("python-default@2",),
        lockfiles=("uv.lock",),
        tools=(ToolDeclaration("uv", ("uv", "--version")),),
    )


def test_gate_executes_dependencies_and_binds_every_declared_input() -> None:
    adapter = Adapter()

    receipt = execute_gate(_graph(), "final", _inputs(), adapter)

    assert adapter.executed == ["core:static", "repository:test"]
    assert receipt.execution.names == ("core:static", "repository:test")
    assert {outcome.status for outcome in receipt.execution.shards} == {"passed"}
    assert {outcome.evidence for outcome in receipt.execution.shards} == {"tree"}
    assert receipt.identity.configuration.path == "signetum.toml"
    assert tuple(lock.path for lock in receipt.identity.lockfiles) == ("uv.lock",)
    assert receipt.identity.tools[0].identity == "uv 0.8.14"


def test_failed_shard_produces_no_gate_evidence() -> None:
    adapter = Adapter(failed="repository:test")

    with pytest.raises(ValidationExecutionError, match="repository:test"):
        execute_gate(_graph(), "final", _inputs(), adapter)


def test_a_failed_shard_does_not_hide_independent_problems() -> None:
    graph = resolve_validation_graph(
        (
            GraphContribution(
                "core",
                shards=(
                    ValidationShard("core:one", ("one",)),
                    ValidationShard("core:two", ("two",)),
                    ValidationShard("core:after", ("after",), ("core:one",)),
                ),
                gates=(GateDeclaration("final", ("core:one", "core:two", "core:after")),),
            ),
        )
    )
    adapter = Adapter(failed="core:one")

    with pytest.raises(ValidationExecutionError) as failure:
        execute_gate(graph, "final", _inputs(), adapter)

    assert "core:one" in str(failure.value)
    assert "core:after: skipped after core:one" in str(failure.value)
    assert adapter.executed == ["core:one", "core:two"]


_WORLD_DOCUMENT = (
    '{"schema_version":1,"findings":['
    '{"id":"GHSA-aaaa-bbbb-cccc","locator":"pip:demo@1.0","summary":"Demo"}]}'
)


def _world_graph() -> ValidationGraph:
    return resolve_validation_graph(
        (
            GraphContribution(
                "core",
                shards=(
                    ValidationShard(
                        "core:audit",
                        ("audit",),
                        (),
                        "world",
                        ("audit", "--findings"),
                    ),
                ),
                gates=(GateDeclaration("final", ("core:audit",)),),
            ),
        )
    )


def _waiver(**overrides: object) -> Waiver:
    values: dict[str, object] = {
        "schema_version": 1,
        "id": "audit-demo",
        "shard": "core:audit",
        "findings": ("GHSA-aaaa-bbbb-cccc",),
        "reason": "Upstream fix pending",
        "approved_by": "maintainer",
        "expires": date(2026, 12, 31),
    }
    values.update(overrides)
    return Waiver.model_validate(values)


def _world_inputs(*waivers: Waiver) -> ValidationInputs:
    return ValidationInputs(
        configuration_path="signetum.toml",
        profiles=(),
        lockfiles=("uv.lock",),
        tools=(),
        waivers=waivers,
        today=date(2026, 9, 2),
    )


def test_a_live_waiver_records_a_world_shard_as_waived_rather_than_passed() -> None:
    adapter = Adapter(failed="core:audit", document=_WORLD_DOCUMENT)

    receipt = execute_gate(_world_graph(), "final", _world_inputs(_waiver()), adapter)

    outcome = receipt.execution.shards[0]
    assert outcome.status == "waived"
    assert outcome.evidence == "world"
    assert outcome.waivers == ("audit-demo",)
    assert outcome.findings == ("GHSA-aaaa-bbbb-cccc",)
    assert outcome.observed_at is not None
    assert receipt.completeness.world_shards == ("core:audit",)


def test_a_passing_world_shard_is_not_waived() -> None:
    adapter = Adapter(document=_WORLD_DOCUMENT)

    receipt = execute_gate(_world_graph(), "final", _world_inputs(), adapter)

    outcome = receipt.execution.shards[0]
    assert outcome.status == "passed"
    assert outcome.waivers == ()
    assert outcome.observed_at is not None


@pytest.mark.parametrize(
    ("waivers", "document", "expected"),
    [
        pytest.param((), _WORLD_DOCUMENT, "uncovered", id="no-waiver"),
        pytest.param(
            (_waiver(expires=date(2026, 9, 1)),),
            _WORLD_DOCUMENT,
            "expired waivers",
            id="expired-waiver",
        ),
        pytest.param(
            (_waiver(findings=("GHSA-dddd-eeee-ffff",)),),
            _WORLD_DOCUMENT,
            "uncovered",
            id="waiver-for-another-finding",
        ),
        pytest.param(
            (_waiver(shard="core:other"),),
            _WORLD_DOCUMENT,
            "uncovered",
            id="waiver-for-another-shard",
        ),
        pytest.param(
            (_waiver(),),
            '{"schema_version":1,"findings":[]}',
            "unwaived",
            id="failure-explains-nothing",
        ),
        pytest.param((_waiver(),), "not json", "not JSON", id="unparsable-document"),
    ],
)
def test_an_unexplained_world_failure_still_fails_its_gate(
    waivers: tuple[Waiver, ...], document: str, expected: str
) -> None:
    adapter = Adapter(failed="core:audit", document=document)

    with pytest.raises(ValidationExecutionError, match=expected):
        execute_gate(_world_graph(), "final", _world_inputs(*waivers), adapter)


def test_a_world_shard_without_a_findings_command_cannot_be_waived() -> None:
    graph = resolve_validation_graph(
        (
            GraphContribution(
                "core",
                shards=(ValidationShard("core:audit", ("audit",), (), "world"),),
                gates=(GateDeclaration("final", ("core:audit",)),),
            ),
        )
    )
    adapter = Adapter(failed="core:audit", document=_WORLD_DOCUMENT)

    with pytest.raises(ValidationExecutionError, match="declares no findings command"):
        execute_gate(graph, "final", _world_inputs(_waiver()), adapter)


@pytest.mark.parametrize(
    "inputs",
    [
        lambda: ValidationInputs("other.toml", (), (), ()),
        lambda: ValidationInputs("signetum.toml", ("z@1", "a@1"), (), ()),
        lambda: ValidationInputs("signetum.toml", (), ("z.lock", "a.lock"), ()),
        lambda: ValidationInputs(
            "signetum.toml",
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
