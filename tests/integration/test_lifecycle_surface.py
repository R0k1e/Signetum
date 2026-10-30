"""Lifecycle vocabulary is bounded; maintenance has a separate local boundary."""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum import lifecycle
from signetum.runtime_generation import generate_runtime

MAINTENANCE = ("workspace-sync", "worktree-prepare", "cleanup", "batch-discard")


@pytest.mark.parametrize("command", MAINTENANCE)
def test_lifecycle_refuses_maintenance_commands(tmp_path, monkeypatch, capsys, command):
    monkeypatch.chdir(tmp_path)
    assert lifecycle.main([command]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "invalid"
    assert "invalid choice" in result["cause"]


@pytest.mark.parametrize("backend", ["signetum", "_signetum_runtime"])
def test_maintenance_preparation_dispatches_existing_authority(
    tmp_path, monkeypatch, capsys, backend
):
    if backend == "_signetum_runtime":
        generate_runtime(tmp_path)
        monkeypatch.syspath_prepend(str(tmp_path / ".agents/signetum/runtime"))
    module = importlib.import_module(backend + ".maintenance")
    calls = []

    def prepare(path):
        calls.append(path)
        return {"prepared": str(path)}

    monkeypatch.setattr(module, "worktree_prepare", prepare)
    monkeypatch.chdir(tmp_path)
    assert module.main(["worktree-prepare", "."]) == 0
    assert calls == [tmp_path]
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


@pytest.mark.parametrize("entry", ["lifecycle", "maintenance"])
def test_template_entrypoint_runs_without_engine_or_site_packages(tmp_path, entry):
    root = Path(__file__).parents[2]
    # The rendered entrypoint imports only its bundled generated authority.
    script = root / "tests/fixtures/portable-python/.agents/signetum/runtime" / (entry + ".py")
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and repository-owned entrypoint
        [sys.executable, "-I", "-S", str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if entry == "lifecycle":
        for command in MAINTENANCE:
            assert command not in result.stdout
        for command in (
            "workspace-open",
            "changed",
            "ready",
            "batch-open",
            "batch-admit",
            "batch-continue",
            "final",
            "batch-deliver",
        ):
            assert command in result.stdout
    else:
        for command in MAINTENANCE:
            assert command in result.stdout
