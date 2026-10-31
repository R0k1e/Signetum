"""Both lifecycle entrypoints preserve the same result and error contract."""

import importlib
import json
from pathlib import Path

import pytest
from signetum import lifecycle
from signetum import lifecycle as core_lifecycle


@pytest.fixture(params=["engine"])
def frontend(request):
    return lifecycle if request.param == "engine" else core_lifecycle


@pytest.mark.parametrize(
    ("category", "status", "exit_code"),
    [
        ("AdmissionError", "invalid", 2),
        ("ValidationExecutionError", "failed", 3),
        ("ValidationInfrastructureError", "infrastructure_error", 4),
        ("OSError", "infrastructure_error", 4),
        ("OperationFailed", "failed", 3),
        ("InfrastructureError", "infrastructure_error", 4),
        ("MergeConflict", "conflict", 5),
    ],
)
def test_native_cli_classifies_failure_and_retains_one_result(
    frontend, category, status, exit_code, tmp_path, monkeypatch, capsys
):
    execution = importlib.import_module("signetum.validation.execution")
    operations = importlib.import_module("signetum.operations")
    errors = {
        "OSError": OSError,
        "AdmissionError": frontend.AdmissionError,
        "ValidationExecutionError": execution.ValidationExecutionError,
        "ValidationInfrastructureError": execution.ValidationInfrastructureError,
        "OperationFailed": operations.OperationFailed,
        "InfrastructureError": operations.InfrastructureError,
        "MergeConflict": operations.MergeConflict,
    }
    error = errors[category]("observed failure")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(frontend, "changed", fail)
    monkeypatch.setattr(frontend, "_state_root", lambda repository: tmp_path)
    assert frontend.main(["changed"]) == exit_code
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    result = json.loads(captured.out)
    assert result["schema_version"] == 1
    assert result["operation"] == "changed"
    assert result["status"] == status
    assert result["exit_code"] == exit_code
    assert result["cause"] == str(error)
    assert result["context"] == {"operation": "changed"}
    assert result["expected"]
    assert Path(result["log"]).read_text() == str(error) + "\n"
    assert str(error) in captured.err


def test_native_cli_preserves_business_outcome_inside_success(frontend, monkeypatch, capsys):
    monkeypatch.setattr(
        frontend, "changed", lambda *a, **k: {"status": "selection-only", "executed": []}
    )
    assert frontend.main(["changed", "--explain"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "schema_version": 1,
        "operation": "changed",
        "status": "passed",
        "exit_code": 0,
        "outcome": "selection-only",
        "executed": [],
    }


def test_native_cli_invalid_arguments_are_one_json_refusal(frontend, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(frontend, "_state_root", lambda repository: tmp_path)
    assert frontend.main(["batch-deliver"]) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "invalid"
    assert result["operation"] == "batch-deliver"
    assert result["exit_code"] == 2


def test_missing_git_is_infrastructure_without_a_log_authority(frontend, monkeypatch, capsys):
    git = importlib.import_module("signetum.git")
    monkeypatch.setattr(git, "which", lambda executable: None)
    assert frontend.main(["changed"]) == 4
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "infrastructure_error"
    assert "Git executable is unavailable" in result["cause"]
    assert result["log"] is None


def test_missing_host_launcher_is_infrastructure(frontend, tmp_path, monkeypatch, capsys):
    launcher = importlib.import_module("signetum.worktrunk")
    monkeypatch.setattr(launcher, "which", lambda executable: None)
    run = launcher.run_tool
    monkeypatch.setattr(frontend, "changed", lambda *a, **k: run(tmp_path, ("wt", "--version")))
    monkeypatch.setattr(frontend, "_state_root", lambda repository: tmp_path)
    assert frontend.main(["changed"]) == 4
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "infrastructure_error"
    assert "Mise executable is unavailable" in result["cause"]
    assert Path(result["log"]).is_file()
