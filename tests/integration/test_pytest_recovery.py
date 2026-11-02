"""Subprocess evidence for failed-node-only serial recovery."""

import json
import os
import subprocess
import sys

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


@pytest.fixture
def runner_command():
    return ["-m", "signetum.validation.pytest_runner"]


@pytest.mark.parametrize("retry", ["pass", "fail", "skip"])
def test_retry_requires_passed_call_and_retains_first_failure(tmp_path, retry, runner_command):
    test = tmp_path / "test_example.py"
    test.write_text(
        "from pathlib import Path\nimport pytest,sys\n"
        "@pytest.mark.parametrize('identity', ['user@example'])\n"
        "def test_flaky(identity):\n"
        "    assert 'signetum' not in sys.modules, 'pytest depends on engine installation'\n"
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
            *runner_command,
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
    assert result.returncode == 1, result.stdout + result.stderr
    defects = json.loads(report.read_text())
    if retry == "pass":
        assert len(defects) == 1
        assert "first failure retained" in str(defects[0]["first_failure"])
    else:
        assert defects == []


@pytest.mark.parametrize("workers", [0, 2])
def test_collection_failure_is_not_retried(tmp_path, workers, runner_command):
    test = tmp_path / "test_broken.py"
    test.write_text("raise RuntimeError('collection failed')\n")
    marker = tmp_path / "must-not-execute"
    (tmp_path / "test_healthy.py").write_text(
        f"from pathlib import Path\ndef test_healthy():\n    Path({str(marker)!r}).touch()\n"
    )
    report = tmp_path / "recovery.json"
    result = subprocess.run(  # noqa: S603 -- isolated Python fixture, no shell
        [
            sys.executable,
            *runner_command,
            "--",
            "-q",
            "-o",
            "addopts=",
            str(tmp_path),
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
    assert result.returncode == 2
    assert "collection failed" in result.stdout
    assert not report.exists()
    assert not marker.exists(), "collection failure must prevent test execution"
    metrics = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.startswith('{"event": "validation.pytest"')
    ]
    assert len(metrics) == 1
    assert metrics[0]["execution_seconds"] == 0


def test_parallel_failure_retries_without_a_worker(tmp_path, runner_command):
    pytest.importorskip("xdist", reason="parallel adapter scenario requires optional pytest-xdist")
    test = tmp_path / "test_parallel.py"
    test.write_text(
        "import os\n"
        "def test_parallel():\n"
        "    assert 'PYTEST_XDIST_WORKER' not in os.environ, 'first parallel failure'\n"
    )
    report = tmp_path / "recovery.json"
    weights = tmp_path / "weights.json"
    weights.write_text(json.dumps({"test_parallel.py::test_parallel": 10}))
    result = subprocess.run(  # noqa: S603 -- isolated Python fixture, no shell
        [
            sys.executable,
            *runner_command,
            "--",
            "-q",
            "-o",
            "addopts=",
            "-n2",
            str(test),
        ],
        env=dict(
            os.environ,
            SIGNETUM_RECOVERY_REPORT=str(report),
            SIGNETUM_VALIDATION_WORKERS="2",
            SIGNETUM_SCHEDULE_FILE=str(weights),
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "first parallel failure" in str(json.loads(report.read_text()))
    metrics = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.startswith('{"event": "validation.pytest"')
    ]
    assert [item["attempt"] for item in metrics] == ["first", "retry"]
    assert all(0 < item["execution_seconds"] <= item["wall_seconds"] for item in metrics)


def test_failed_original_never_writes_success_on_repeated_runs(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitignore").write_text("__pycache__/\n")
    state = tmp_path / "attempts"
    (repository / "signetum.toml").write_text("schema_version = 5\n")
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
    inputs = ValidationInputs("signetum.toml", (), (), ())
    receipts = tmp_path / "receipts"
    for _ in range(2):
        with pytest.raises(ValidationExecutionError, match="recurring contention failure"):
            run_repository_gate(repository, graph, "member", inputs, receipts)
        assert not tuple(receipts.glob("member-*.json"))


def test_weighted_order_runs_every_test_and_reports_success_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNETUM_VALIDATION_WORKERS", "0")
    observed = tmp_path / "order"
    test = tmp_path / "test_order.py"
    test.write_text(
        "from pathlib import Path\n"
        f"OUT=Path({str(observed)!r})\n"
        'def test_light():\n    with OUT.open("a") as f: f.write("light\\n")\n'
        'def test_heavy():\n    with OUT.open("a") as f: f.write("heavy\\n")\n'
    )
    weights = tmp_path / "weights.json"
    weights.write_text(json.dumps({"test_order.py::test_heavy": 100}))
    # Ready qualifies a detached checkout under the system temp directory, and
    # pytest writes this generated file there too. Without an explicit root,
    # pytest 9 uses their common ancestor, so the node id no longer matches
    # the weight key test_order.py::test_heavy.
    command = [
        sys.executable,
        "-m",
        "signetum.validation.pytest_runner",
        "--",
        "-q",
        "-o",
        "addopts=",
        "--rootdir",
        str(tmp_path),
        str(test),
    ]
    result = subprocess.run(  # noqa: S603 -- actual runner, measured hints and private application tests
        command,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, SIGNETUM_SCHEDULE_FILE=str(weights)),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert observed.read_text().splitlines() == ["heavy", "light"]
    events = [json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")]
    cost = next(e for e in events if e.get("event") == "validation.pytest")
    assert cost["workers"] == 0 and cost["phase_seconds"]["call"] >= 0
    conflict = subprocess.run(  # noqa: S603 -- incompatible explicit scheduling refuses before test execution
        [*command, "--dist=loadscope"],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, SIGNETUM_SCHEDULE_FILE=str(weights)),
    )
    assert conflict.returncode != 0
    assert observed.read_text().splitlines() == ["heavy", "light"]
