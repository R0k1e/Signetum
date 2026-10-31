import json
from pathlib import Path

from change_fixtures import consolidated_approval
from signetum import git as git_tools
from signetum.cli import app
from signetum.traceability.boundary import RepositoryInventory
from typer.testing import CliRunner

FIXTURE = Path(__file__).parents[2] / "tests/fixtures/portable-python" / "signetum.toml"


def test_cli_validates_manifest_through_public_command() -> None:
    result = CliRunner().invoke(app, ["validate", "--manifest", str(FIXTURE)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "protocol": 2,
        "manifest_schema": 3,
        "profiles": ["shared-core@1", "python-default@1", "git-worktrunk@1"],
        "status": "valid",
    }


def test_cli_reports_one_json_failure(tmp_path: Path) -> None:
    manifest = tmp_path / "signetum.toml"
    manifest.write_text("schema_version = 99\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["validate", "--manifest", str(manifest)])

    assert result.exit_code == 2
    assert json.loads(result.stdout) == {
        "error": "unsupported manifest schema: 99",
        "status": "invalid",
    }


def test_check_manifest_composes_the_existing_public_contract() -> None:
    result = CliRunner().invoke(app, ["check", "manifest", "--manifest", str(FIXTURE)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "valid"


def test_check_traceability_uses_the_public_query_boundary(tmp_path) -> None:
    repository = tmp_path
    git_tools.git_output(repository, "init", "-b", "main")
    consolidated_approval(repository, "a" * 40)

    result = CliRunner().invoke(
        app,
        [
            "check",
            "traceability",
            "--repository",
            str(repository),
            "--decision-root",
            "decisions",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["valid"] is True
    (repository / "changes").rename(repository / "requests")
    (repository / "signetum.toml").write_text(
        FIXTURE.read_text().replace('changes = "changes"', 'changes = "requests"')
    )
    inferred = CliRunner().invoke(app, ["check", "traceability", "--repository", str(repository)])
    assert inferred.exit_code == 0, inferred.stdout
    assert json.loads(inferred.stdout)["valid"] is True


def test_check_product_surface_reports_one_versioned_result() -> None:
    repository = Path(__file__).parents[2]

    result = CliRunner().invoke(
        app,
        ["check", "product-surface", "--repository", str(repository)],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "issues": [],
        "schema_version": 1,
        "valid": True,
    }


def test_check_product_surface_rejects_an_incomplete_inventory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "signetum.cli.GitInventoryProvider.read",
        lambda self, repository: RepositoryInventory(paths=frozenset()),
    )

    result = CliRunner().invoke(
        app,
        ["check", "product-surface", "--repository", str(tmp_path)],
    )

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["issues"][0]["code"] == "missing-required-asset"


def test_check_product_surface_maps_inventory_failure_to_invocation_result(
    monkeypatch, tmp_path: Path
) -> None:
    def fail(self, repository: Path) -> RepositoryInventory:
        raise OSError("inventory unavailable")

    monkeypatch.setattr("signetum.cli.GitInventoryProvider.read", fail)

    result = CliRunner().invoke(
        app,
        ["check", "product-surface", "--repository", str(tmp_path)],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout) == {
        "error": "inventory unavailable",
        "schema_version": 1,
        "status": "invalid",
    }


def test_release_preflight_reports_a_versioned_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_tools, "which", lambda executable: None)

    result = CliRunner().invoke(
        app,
        ["release", "preflight", "--source", "abc", "--repository", str(tmp_path)],
    )

    assert result.exit_code == 4
    failure = json.loads(result.stdout)
    assert failure["schema_version"] == 1
    assert failure["operation"] == "release-preflight"
    assert failure["status"] == "infrastructure_error"
    assert failure["cause"] == "Git executable is unavailable"
    assert failure["expected"]
