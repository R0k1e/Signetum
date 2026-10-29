"""A diagnostic retry cannot publish success for an originally failed run."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_retry_stays_failed_and_a_fixed_normal_run_passes(tmp_path, frontend):
    marker = tmp_path / "attempt"
    case = tmp_path / "test_case.py"
    case.write_text(
        "from pathlib import Path\n"
        "def test_case():\n"
        f"    marker = Path({str(marker)!r})\n"
        "    first = not marker.exists()\n"
        "    marker.touch()\n"
        "    assert not first, 'original execution defect'\n"
    )
    runtime = Path(__file__).parents[2] / "template/.agents/repo-dev/runtime/_signetum_runtime"
    launcher = (
        ["-m", "signetum.validation.pytest_runner"]
        if frontend == "engine"
        else [str(runtime / "pytest_runner.py")]
    )
    report = tmp_path / "attempts.json"
    argv = [sys.executable, *launcher, "--", "-q", "-o", "addopts=", str(case)]
    failed = subprocess.run(  # noqa: S603 -- real public runner and disposable test
        argv,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, SIGNETUM_RECOVERY_REPORT=str(report), SIGNETUM_VALIDATION_WORKERS="0"),
    )
    assert failed.returncode == 1, failed.stdout + failed.stderr
    assert "1 passed" in failed.stdout, "diagnostic retry did not execute"
    assert "original execution defect" in str(json.loads(report.read_text()))

    case.write_text("def test_case():\n    assert 2 + 2 == 4\n")
    fixed = subprocess.run(  # noqa: S603 -- fresh normal run after changing the source
        argv,
        capture_output=True,
        text=True,
        check=False,
        env=dict(
            os.environ,
            SIGNETUM_RECOVERY_REPORT=str(tmp_path / "fresh.json"),
            SIGNETUM_VALIDATION_WORKERS="0",
        ),
    )
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    measured = [json.loads(line) for line in fixed.stderr.splitlines() if line.startswith("{")]
    cost = next(item for item in measured if item.get("event") == "validation.pytest")
    assert cost["exit_code"] == 0 and cost["workers"] == 0
    assert cost["collection_seconds"] >= 0 and cost["execution_seconds"] >= 0
    assert cost["phase_seconds"]["call"] >= 0
    assert any(item.get("event") == "validation.pytest.cleanup" for item in measured)
