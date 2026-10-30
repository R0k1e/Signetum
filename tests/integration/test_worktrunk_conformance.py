"""Portable host-tool effects match the engine without importing it."""

import importlib
import subprocess
import sys
import time

import pytest
from test_lifecycle_conformance import _template_lifecycle

from signetum import worktrunk


@pytest.fixture(params=["engine", "template"])
def launcher(request):
    if request.param == "engine":
        return worktrunk
    _template_lifecycle()
    return importlib.import_module("_signetum_runtime.worktrunk")


@pytest.mark.parametrize("required", [True, False])
def test_host_launcher_deadline_terminates_descendants(launcher, required, tmp_path, monkeypatch):
    shim = tmp_path / "mise"
    shim.write_text('#!/bin/sh\nshift\nshift\nexec "$@"\n')
    shim.chmod(0o700)
    monkeypatch.setattr(launcher, "mise_executable", lambda: str(shim))
    marker = tmp_path / "orphan"
    child = "import sys,time; from pathlib import Path; time.sleep(2); Path(sys.argv[1]).touch()"
    parent = "import subprocess,sys; subprocess.run([sys.executable,'-c',sys.argv[1],sys.argv[2]])"
    error = launcher.InfrastructureError if required else subprocess.TimeoutExpired
    with pytest.raises(error):
        launcher.run_tool(
            tmp_path,
            (sys.executable, "-c", parent, child, str(marker)),
            timeout_seconds=0.5,
            required=required,
        )
    time.sleep(2)
    assert not marker.exists(), "the host launcher left its descendant running"


def test_host_projection_preserves_explicit_inputs_and_clears_foreign_context(
    launcher, tmp_path, monkeypatch
):
    seen = {}

    def observe(repository, command, *, timeout_seconds, environment):
        seen.update(environment)
        assert command == ("/fixture/mise", "exec", "--", "uv", "--version")
        assert repository == tmp_path
        assert timeout_seconds == 1800
        return subprocess.CompletedProcess(command, 0, "identity", "")

    monkeypatch.setattr(launcher, "mise_executable", lambda: "/fixture/mise")
    monkeypatch.setattr(launcher, "run_command", observe)
    result = launcher.run_tool(
        tmp_path, ("uv", "--version"), environment={"GIT_DIR": "/foreign", "KEEP": "yes"}
    )
    assert result.stdout == "identity"
    assert "GIT_DIR" not in seen
    assert seen["KEEP"] == "yes"
    assert seen["MISE_TRUSTED_CONFIG_PATHS"] == str(tmp_path.resolve())
