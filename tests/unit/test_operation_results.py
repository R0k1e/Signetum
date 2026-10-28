"""Lifecycle consumers receive one JSON result and an actionable status."""

import argparse
import json
from pathlib import Path

import pytest
import yaml

from signetum import lifecycle
from signetum.operations import InfrastructureError, MergeConflict, OperationFailed


@pytest.mark.parametrize(
    ("error", "status", "exit_code"),
    [
        (lifecycle.AdmissionError("wrong base"), "invalid", 2),
        (lifecycle.ValidationExecutionError("check failed"), "failed", 3),
        (OperationFailed("push rejected"), "failed", 3),
        (InfrastructureError("tool unavailable"), "infrastructure_error", 4),
        (
            lifecycle.ValidationInfrastructureError("identity unavailable"),
            "infrastructure_error",
            4,
        ),
        (MergeConflict("open merge", expected="batch-continue batch"), "conflict", 5),
    ],
)
def test_cli_failure_has_one_result_and_retained_diagnostic(
    error, status, exit_code, monkeypatch, capsys, tmp_path: Path
):
    def fail(*args):
        raise error

    monkeypatch.setattr(lifecycle, "validate", fail)
    monkeypatch.setattr(lifecycle, "_state_root", lambda repository: tmp_path)
    assert lifecycle.main(["final"]) == exit_code
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result["status"] == status
    assert result["exit_code"] == exit_code
    assert result["operation"] == "final"
    assert result["cause"] == str(error)
    assert result["context"] == {"operation": "final"}
    assert result["expected"]
    assert Path(result["log"]).read_text() == str(error) + "\n"
    assert str(error) in captured.err


def test_cli_success_keeps_business_outcome_in_one_envelope(monkeypatch, capsys):
    monkeypatch.setattr(
        lifecycle, "changed", lambda *args, **kwargs: {"status": "changed", "files": []}
    )
    assert lifecycle.main(["changed"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "schema_version": 1,
        "operation": "changed",
        "status": "passed",
        "exit_code": 0,
        "outcome": "changed",
        "files": [],
    }


def test_invalid_arguments_are_a_json_precondition_refusal(capsys):
    assert lifecycle.main(["batch-deliver"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["operation"] == "batch-deliver"
    assert result["status"] == "invalid"


def test_repository_catalog_matches_registered_lifecycle_commands():
    root = Path(__file__).resolve().parents[2]
    policy = yaml.safe_load((root / ".agents/repo-dev/repo.yaml").read_text())
    declared = policy["repository"]["lifecycle"]["public_operations"]
    parser = lifecycle._parser()
    registered = next(
        action.choices
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    assert tuple(registered) == tuple(declared)
