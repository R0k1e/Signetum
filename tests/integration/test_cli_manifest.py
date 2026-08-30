import json
from pathlib import Path

from typer.testing import CliRunner

from development_foundation.cli import app

FIXTURE = Path(__file__).parents[1] / "fixtures" / "repository.yaml"


def test_cli_validates_manifest_through_public_command() -> None:
    result = CliRunner().invoke(app, ["validate", "--manifest", str(FIXTURE)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "foundation": "2.0.0",
        "manifest_schema": 1,
        "profiles": ["shared-core@1", "python-uv@1", "git-worktrunk@1"],
        "status": "valid",
    }


def test_cli_reports_one_json_failure(tmp_path: Path) -> None:
    manifest = tmp_path / "repository.yaml"
    manifest.write_text("schema_version: 99\n", encoding="utf-8")

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


def test_check_traceability_uses_the_public_query_boundary() -> None:
    repository = Path(__file__).parents[1] / "fixtures" / "changes" / "valid"

    result = CliRunner().invoke(
        app,
        ["check", "traceability", "--repository", str(repository)],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["valid"] is True
