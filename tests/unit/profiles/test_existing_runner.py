"""Optional language adapters preserve existing runners rather than inventing them."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture(params=["signetum.profiles.existing_runner", "_signetum_runtime.existing_runner"])
def adapter(request, monkeypatch):
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[3] / "tests/fixtures/portable-python/.agents/signetum/runtime")
    )
    return importlib.import_module(request.param)


@pytest.mark.parametrize("language", ["python", "node", "rust"])
def test_existing_runner_keeps_literal_arguments_and_declared_tool_identity(adapter, language):
    command = ("existing-runner", "test", "literal;$(not-a-command)", "path with spaces")
    tool = adapter.ToolDeclaration("existing-runner", ("existing-runner", "--version"))
    request = adapter.ExistingRunnerRequest(language=language, command=command, tools=(tool,))
    binding = adapter.existing_runner_validation(request)
    assert binding.identity == f"{language}-existing@1"
    assert binding.validation.shards[0].command == command
    assert binding.validation.tools == (tool,)
    assert {item.name for item in binding.validation.gates} == {"member", "final"}
    assert binding.validation.member_required == (binding.validation.shards[0].name,)
    assert binding.validation.shards[0].evidence == "tree"


@pytest.mark.parametrize(
    "damage", ["language", "empty-command", "empty-tools", "duplicate-tools", "timeout"]
)
def test_invalid_bindings_are_refused_before_any_execution(adapter, damage):
    tool = adapter.ToolDeclaration("existing", ("existing", "--version"))
    data: dict[str, object] = {
        "language": "node",
        "command": ("existing", "test"),
        "tools": (tool,),
    }
    if damage == "language":
        data["language"] = "unknown"
    elif damage == "empty-command":
        data["command"] = ()
    elif damage == "empty-tools":
        data["tools"] = ()
    elif damage == "duplicate-tools":
        data["tools"] = (tool, tool)
    else:
        data["timeout_seconds"] = 0
    with pytest.raises(ValueError):
        adapter.existing_runner_validation(adapter.ExistingRunnerRequest(**data))
