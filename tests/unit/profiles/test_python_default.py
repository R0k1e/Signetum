from reposeal.profiles.python_default import PythonDefaultPaths, python_default_validation


def test_python_default_contributes_configurable_validation_mapping() -> None:
    configuration = python_default_validation(
        PythonDefaultPaths(
            source=("packages/api", "packages/worker"),
            unit=("checks/unit",),
            integration=("checks/integration",),
        )
    )

    shards = {shard["name"]: shard for shard in configuration["shards"]}
    gates = {gate["name"]: gate["shards"] for gate in configuration["gates"]}

    assert shards["profile:python-default@1:ruff"]["command"][-2:] == [
        "packages/api",
        "packages/worker",
    ]
    assert shards["profile:python-default@1:unit"]["command"][-1:] == ["checks/unit"]
    assert shards["profile:python-default@1:integration"]["command"][-1:] == ["checks/integration"]
    assert "profile:python-default@1:dependency-audit" in gates["final"]
    assert "profile:python-default@1:secrets" in gates["member"]


def test_python_default_mapping_is_independent_of_other_profiles() -> None:
    configuration = python_default_validation()

    assert configuration["identity"] == "python-default@1"
    assert {tool["name"] for tool in configuration["tools"]} == {
        "detect-secrets",
        "mise",
        "pip-audit",
        "python",
        "ruff",
        "ty",
        "uv",
    }
    assert all(
        shard["name"].startswith("profile:python-default@1:") for shard in configuration["shards"]
    )
