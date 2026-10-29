"""Owned detached leaks fail successful commands without harming other jobs."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from signetum.validation import process_observation


@pytest.fixture(params=["engine", "template"])
def runner(request, monkeypatch):
    if request.param == "engine":
        return importlib.import_module("signetum.validation.process")
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[3] / "template/.agents/repo-dev/runtime")
    )
    return importlib.import_module("_signetum_runtime.process")


@pytest.mark.parametrize("exit_code", [0, 7])
def test_detached_leak_is_cleaned_and_never_publishes_success(tmp_path, runner, exit_code):
    child = "import time; time.sleep(30)"
    script = (
        "import subprocess,sys; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
        "print(p.pid,flush=True); "
        f"sys.exit({exit_code})"
    )
    unrelated = subprocess.Popen(  # noqa: S603 -- controlled fixture
        [sys.executable, "-c", child], start_new_session=True
    )
    leaked_pid = None
    try:
        result = runner.run_command(tmp_path, [sys.executable, "-c", script], timeout_seconds=10)
        leaked_pid = int(result.stdout.strip())
        assert result.returncode == (exit_code or 1), result.stderr
        assert "owned process leak" in result.stderr
        assert unrelated.poll() is None
        try:
            identity = process_observation.process_identity(leaked_pid)
        except OSError:
            pass
        else:
            assert identity.zombie
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
        if leaked_pid is not None:
            try:
                os.kill(leaked_pid, 9)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("detached", [False, True])
def test_timeout_cleans_owned_descendants(tmp_path, runner, detached):
    pid_file = tmp_path / "child-pid"
    child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)"
    script = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session={detached!r}); "
        f"Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(30)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        runner.run_command(tmp_path, [sys.executable, "-c", script], timeout_seconds=0.8)
    assert pid_file.exists()
    try:
        identity = process_observation.process_identity(int(pid_file.read_text()))
    except OSError:
        pass
    else:
        assert identity.zombie


def test_settlement_does_not_signal_a_reused_pid(monkeypatch):
    observer = process_observation
    original = observer.ProcessIdentity(34567, 34567, 100, os.getuid(), False)
    reused = observer.ProcessIdentity(34567, 34567, 200, os.getuid(), False)
    inventories = iter(
        [
            observer.OwnershipScan((observer.OwnedProcess(original, "owner-token"),), ()),
            observer.OwnershipScan((), ()),
        ]
    )
    monkeypatch.setattr(observer, "observe_owned_processes", lambda *_: next(inventories))
    monkeypatch.setattr(observer, "process_identity", lambda _: reused)
    signals = []
    monkeypatch.setattr(observer.os, "kill", lambda *args: signals.append(args))
    result = observer.settle_owned_processes("a" * 32, 12345)
    assert result.leaked == (34567,)
    assert result.remaining == ()
    assert signals == []


@pytest.mark.parametrize("exit_code", [0, 7])
def test_unavailable_scan_is_infrastructure_without_masking_original_failure(
    monkeypatch, runner, capsys, exit_code
):
    observer = runner._observer()
    monkeypatch.setenv(observer.OWNER_ENV, '["' + "a" * 32 + '"]')
    monkeypatch.setattr(runner.threading.Thread, "start", lambda _: None)
    monkeypatch.setattr(runner.subprocess, "call", lambda _: exit_code)

    def unavailable(*_):
        raise observer.ProcessObservationUnavailable("native inventory unavailable")

    monkeypatch.setattr(observer, "settle_owned_processes", unavailable)
    assert runner.main(["0", "--", "unused-fixture-command"]) == (exit_code or 126)
    assert "process observation unavailable" in capsys.readouterr().err
