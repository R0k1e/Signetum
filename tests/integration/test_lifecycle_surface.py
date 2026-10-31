"""Lifecycle vocabulary is bounded; maintenance has a separate local boundary."""

import importlib
import json

import pytest
from signetum import lifecycle

MAINTENANCE = ("workspace-sync", "worktree-prepare", "cleanup", "batch-discard")


@pytest.mark.parametrize("command", MAINTENANCE)
def test_lifecycle_refuses_maintenance_commands(tmp_path, monkeypatch, capsys, command):
    monkeypatch.chdir(tmp_path)
    assert lifecycle.main([command]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "invalid"
    assert "invalid choice" in result["cause"]


@pytest.mark.parametrize("backend", ["signetum"])
def test_maintenance_preparation_dispatches_existing_authority(
    tmp_path, monkeypatch, capsys, backend
):
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
