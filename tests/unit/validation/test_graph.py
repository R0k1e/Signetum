from collections.abc import Callable

import pytest

from signetum.validation import (
    GateDeclaration,
    GraphContribution,
    ValidationConfiguration,
    ValidationGraphError,
    ValidationShard,
    resolve_tools,
    resolve_validation_graph,
)


def test_graph_composes_namespaced_shards_in_dependency_order() -> None:
    graph = resolve_validation_graph(
        (
            GraphContribution(
                identity="core",
                shards=(ValidationShard("core:static", ("check", "static")),),
                gates=(GateDeclaration("member", ("core:static",)),),
            ),
            GraphContribution(
                identity="profile:go@1",
                shards=(
                    ValidationShard("profile:go@1:test", ("go", "test", "./..."), ("core:static",)),
                ),
                gates=(GateDeclaration("final", ("profile:go@1:test",)),),
            ),
            GraphContribution(
                identity="repository",
                gates=(GateDeclaration("final", ("core:static",)),),
            ),
        )
    )

    assert graph.gate("member").shards == ("core:static",)
    assert graph.gate("final").shards == ("core:static", "profile:go@1:test")
    assert graph.execution_order("final") == ("core:static", "profile:go@1:test")
    assert graph.digest.startswith("sha256:")


def test_graph_rejects_duplicate_shard_ownership() -> None:
    shard = ValidationShard("profile:go@1:test", ("go", "test", "./..."))

    with pytest.raises(ValidationGraphError, match="duplicate shard owner"):
        resolve_validation_graph(
            (
                GraphContribution(identity="profile:go@1", shards=(shard,)),
                GraphContribution(identity="repository", shards=(shard,)),
            )
        )


def test_graph_rejects_missing_and_cyclic_dependencies() -> None:
    with pytest.raises(ValidationGraphError, match="unknown shard"):
        resolve_validation_graph(
            (
                GraphContribution(
                    identity="repository",
                    gates=(GateDeclaration("final", ("missing:test",)),),
                ),
            )
        )

    with pytest.raises(ValidationGraphError, match="cyclic shard dependency"):
        resolve_validation_graph(
            (
                GraphContribution(
                    identity="repository",
                    shards=(
                        ValidationShard("repository:a", ("a",), ("repository:b",)),
                        ValidationShard("repository:b", ("b",), ("repository:a",)),
                    ),
                    gates=(GateDeclaration("final", ("repository:a",)),),
                ),
            )
        )


def test_tool_composition_rejects_ambiguous_ownership() -> None:
    first = ValidationConfiguration.from_mapping(
        "core",
        {"tools": [{"name": "git", "identity_command": ["git", "--version"]}]},
    )
    second = ValidationConfiguration.from_mapping(
        "repository",
        {"tools": [{"name": "git", "identity_command": ["other-git", "--version"]}]},
    )

    with pytest.raises(ValidationGraphError, match="duplicate tool owner"):
        resolve_tools((first, second))


def test_mapping_adapter_validates_complete_declarative_configuration() -> None:
    configuration = ValidationConfiguration.from_mapping(
        "repository",
        {
            "tools": [{"name": "go", "identity_command": ["go", "version"]}],
            "shards": [
                {
                    "name": "repository:test",
                    "command": ["go", "test", "./..."],
                    "requires": [],
                }
            ],
            "gates": [{"name": "member", "shards": ["repository:test"]}],
        },
    )

    assert configuration.contribution.shards[0].command == ("go", "test", "./...")
    assert configuration.contribution.gates[0].shards == ("repository:test",)
    assert configuration.tools[0].identity_command == ("go", "version")


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"shards": "bad"}, "shards must be an object array"),
        ({"gates": "bad"}, "gates must be an object array"),
        ({"tools": "bad"}, "tools must be an object array"),
        ({"shards": ["bad"]}, "shards must be an object array"),
        ({"shards": [{}]}, "shard.name must be a string"),
        ({"shards": [{"name": "repository:test", "command": "bad"}]}, "string array"),
        ({"gates": ["bad"]}, "gates must be an object array"),
        ({"gates": [{}]}, "gate.name must be a string"),
        ({"tools": ["bad"]}, "tools must be an object array"),
        ({"tools": [{}]}, "tool.name must be a string"),
        (
            {"tools": [{"name": "git", "identity_command": ["git"]}] * 2},
            "duplicate tool owner in contribution",
        ),
    ],
)
def test_mapping_adapter_rejects_invalid_shapes(document: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationGraphError, match=message):
        ValidationConfiguration.from_mapping("repository", document)


@pytest.mark.parametrize(
    "operation",
    [
        lambda: ValidationShard("not-namespaced", ("check",)),
        lambda: ValidationShard("core:test", ()),
        lambda: ValidationShard("core:test", ("check",), ("core:static", "core:static")),
        lambda: GateDeclaration("INVALID", ("core:test",)),
        lambda: GateDeclaration("final", ("core:test", "core:test")),
        lambda: GraphContribution(""),
        lambda: ValidationConfiguration.from_mapping(
            "repository", {"tools": [{"name": "", "identity_command": ["tool"]}]}
        ),
    ],
)
def test_declarations_reject_invalid_values(operation: Callable[[], object]) -> None:
    with pytest.raises(ValidationGraphError):
        operation()
