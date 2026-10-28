"""Subprocess evidence for failed-node-only serial recovery."""

import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest

from signetum.git import git_output
from signetum.validation import (
    GateDeclaration,
    GraphContribution,
    ValidationShard,
    resolve_validation_graph,
)
from signetum.validation.execution import ValidationExecutionError, ValidationInputs
from signetum.validation.repository import run_repository_gate


@pytest.mark.parametrize("retry", ["pass", "fail", "skip"])
def test_retry_requires_passed_call_and_retains_first_failure(tmp_path, retry):
    test = tmp_path / "test_example.py"
    test.write_text(
        "from pathlib import Path\nimport pytest\n"
        "@pytest.mark.parametrize('identity', ['user@example'])\n"
        "def test_flaky(identity):\n"
        "    marker = Path(__file__).with_suffix('.attempt')\n"
        "    first = not marker.exists()\n"
        "    marker.touch()\n"
        "    if first: assert False, 'first failure retained'\n"
        + ("    pytest.skip('cannot prove recovery')\n" if retry == "skip" else "")
        + ("    assert False, 'persistent failure'\n" if retry == "fail" else "")
        + "def test_unrelated():\n"
        "    marker = Path(__file__).with_suffix('.unrelated')\n"
        "    assert not marker.exists(), 'unrelated test ran twice'\n"
        "    marker.touch()\n"
    )
    report = tmp_path / "recovery.json"
    result = subprocess.run(  # noqa: S603 -- isolated Python fixture, no shell
        [
            sys.executable,
            "-m",
            "signetum.validation.pytest_runner",
            "--",
            "-q",
            "-o",
            "addopts=",
            str(test),
        ],
        env=dict(os.environ, SIGNETUM_RECOVERY_REPORT=str(report)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if retry == "pass" else 1), result.stdout + result.stderr
    defects = json.loads(report.read_text())
    if retry == "pass":
        assert len(defects) == 1
        assert "first failure retained" in str(defects[0]["first_failure"])
    else:
        assert defects == []


@pytest.mark.parametrize("workers", [0, 2])
def test_collection_failure_is_not_retried(tmp_path, workers):
    test = tmp_path / "test_broken.py"
    test.write_text("raise RuntimeError('collection failed')\n")
    report = tmp_path / "recovery.json"
    result = subprocess.run(  # noqa: S603 -- isolated Python fixture, no shell
        [
            sys.executable,
            "-m",
            "signetum.validation.pytest_runner",
            "--",
            "-q",
            "-o",
            "addopts=",
            str(test),
        ],
        env=dict(
            os.environ,
            SIGNETUM_RECOVERY_REPORT=str(report),
            SIGNETUM_VALIDATION_WORKERS=str(workers),
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (1 if workers else 2)
    assert "collection failed" in result.stdout
    assert not report.exists()


def test_parallel_failure_retries_without_a_worker(tmp_path):
    pytest.importorskip("xdist", reason="parallel adapter scenario requires optional pytest-xdist")
    test = tmp_path / "test_parallel.py"
    test.write_text(
        "import os\n"
        "def test_parallel():\n"
        "    assert 'PYTEST_XDIST_WORKER' not in os.environ, 'first parallel failure'\n"
    )
    report = tmp_path / "recovery.json"
    result = subprocess.run(  # noqa: S603 -- isolated Python fixture, no shell
        [
            sys.executable,
            "-m",
            "signetum.validation.pytest_runner",
            "--",
            "-q",
            "-o",
            "addopts=",
            "-n2",
            str(test),
        ],
        env=dict(os.environ, SIGNETUM_RECOVERY_REPORT=str(report)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "first parallel failure" in str(json.loads(report.read_text()))


def test_recovered_defect_is_in_receipt_and_repeated_member_recovery_fails(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitignore").write_text("__pycache__/\n")
    state = tmp_path / "attempts"
    (repository / "signetum.toml").write_text("schema_version = 2\n")
    (repository / "test_retry.py").write_text(
        "from pathlib import Path\n"
        "def test_retry():\n"
        f"    state = Path({str(state)!r})\n"
        "    n = int(state.read_text()) if state.exists() else 0\n"
        "    state.write_text(str(n + 1))\n"
        "    assert n % 2, 'recurring contention failure'\n"
    )
    git_output(repository, "init")
    git_output(repository, "add", ".")
    git_output(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    graph = resolve_validation_graph(
        (
            GraphContribution(
                "test",
                (
                    ValidationShard(
                        "test:pytest",
                        (
                            sys.executable,
                            "-m",
                            "signetum.validation.pytest_runner",
                            "--",
                            "-q",
                            "-o",
                            "addopts=",
                            "test_retry.py",
                        ),
                    ),
                ),
                (GateDeclaration("member", ("test:pytest",)),),
            ),
        )
    )
    inputs = ValidationInputs("signetum.toml", (), (), (), recovery_threshold=2)
    receipts = tmp_path / "receipts"
    receipt, _ = run_repository_gate(repository, graph, "member", inputs, receipts)
    assert "recurring contention failure" in str(receipt.extensions["recovered_flake_defects"])
    with pytest.raises(ValidationExecutionError, match="repeated recovered robustness defect"):
        run_repository_gate(repository, graph, "member", inputs, receipts)
    bounded, _ = run_repository_gate(
        repository, graph, "member", replace(inputs, recovery_window=1), receipts
    )
    assert bounded.valid
