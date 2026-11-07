"""A diagnostic retry cannot publish success for an originally failed run."""

import json
import subprocess
import sys


def test_retry_stays_failed_and_a_fixed_normal_run_passes(tmp_path):
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
    launcher = ["-m", "signetum.validation.pytest_runner"]
    report = tmp_path / "attempts.json"

    def argv(recovery):
        return [
            sys.executable,
            *launcher,
            "--recovery-report",
            str(recovery),
            "--workers",
            "0",
            "--",
            "-q",
            "-o",
            "addopts=",
            str(case),
        ]

    failed = subprocess.run(  # noqa: S603 -- real public runner and disposable test
        argv(report), capture_output=True, text=True, check=False
    )
    assert failed.returncode == 1, failed.stdout + failed.stderr
    assert "1 passed" in failed.stdout, "diagnostic retry did not execute"
    assert "original execution defect" in str(json.loads(report.read_text()))

    case.write_text("def test_case():\n    assert 2 + 2 == 4\n")
    fixed = subprocess.run(  # noqa: S603 -- fresh normal run after changing the source
        argv(tmp_path / "fresh.json"), capture_output=True, text=True, check=False
    )
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    measured = [json.loads(line) for line in fixed.stderr.splitlines() if line.startswith("{")]
    cost = next(item for item in measured if item.get("event") == "validation.pytest")
    assert cost["exit_code"] == 0 and cost["workers"] == 0
    assert cost["collection_seconds"] >= 0 and cost["execution_seconds"] >= 0
    assert cost["phase_seconds"]["call"] >= 0
    assert any(item.get("event") == "validation.pytest.cleanup" for item in measured)
