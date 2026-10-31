"""Default pytest scratch preserves ownership without overriding repository settings."""

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["engine"])
def command_owner(request, monkeypatch):
    monkeypatch.setenv("SIGNETUM_VALIDATION_WORKERS", "0")
    if request.param == "engine":
        return importlib.import_module("signetum.validation.process")
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[2] / "tests/fixtures/portable-python/.agents/signetum/runtime")
    )
    return importlib.import_module("signetum.validation.process")


@pytest.mark.parametrize("workers", [0, 2])
def test_default_pytest_scratch_finds_environment_scrubbed_detached_leak(
    tmp_path, command_owner, workers, monkeypatch
):
    monkeypatch.setenv("SIGNETUM_VALIDATION_WORKERS", str(workers))
    case = tmp_path / "test_leak.py"
    observed = tmp_path / "observed-scratch"
    width = tmp_path / "observed-width"
    case.write_text(
        "import os,subprocess,sys\nfrom pathlib import Path\n"
        "def test_leak(tmp_path):\n"
        f"    Path({str(observed)!r}).write_text(str(tmp_path))\n"
        f"    Path({str(width)!r}).write_text(os.environ.get('PYTEST_XDIST_WORKER_COUNT', '0'))\n"
        "    subprocess.Popen([sys.executable,'-c','import time; time.sleep(3)'],"
        "cwd=tmp_path,env={},start_new_session=True)\n"
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    runner = Path(command_owner.__file__).with_name("pytest_runner.py")
    result = command_owner.run_command(
        tmp_path,
        [sys.executable, str(runner), "--", "-q", "-n", str(workers), str(case)],
        timeout_seconds=15,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert width.read_text() == str(workers)
    assert "owned process leak" in result.stderr
    assert "signetum-job-" in observed.read_text()
    assert not Path(observed.read_text()).exists()


@pytest.mark.parametrize("location", ["cli", "configuration"])
def test_explicit_pytest_basetemp_keeps_repository_precedence(tmp_path, command_owner, location):
    expected = tmp_path / "repository-owned-temporary-root"
    case = tmp_path / "test_location.py"
    case.write_text(
        "from pathlib import Path\n"
        "def test_location(tmp_path):\n"
        f"    assert tmp_path.is_relative_to(Path({str(expected)!r}))\n"
    )
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\n" + (f"addopts = --basetemp={expected}\n" if location == "configuration" else "")
    )
    runner = Path(command_owner.__file__).with_name("pytest_runner.py")
    arguments = [sys.executable, str(runner), "--", "-q", str(case)]
    if location == "cli":
        arguments.extend(["--basetemp", str(expected)])
    result = command_owner.run_command(tmp_path, arguments, timeout_seconds=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert expected.is_dir()
