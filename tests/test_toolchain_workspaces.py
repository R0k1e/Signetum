"""Behavior tests for the Mise and Worktrunk execution boundary."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

import signetum.worktrunk as wt


def test_missing_mise_has_an_actionable_noninteractive_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr(wt, "which", lambda executable: None)

    with pytest.raises(wt.InfrastructureError, match="install Mise"):
        wt.run_tool(Path.cwd(), ("uv", "--version"))


def test_invalid_worktrunk_json_is_refused(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        wt,
        "run_tool",
        lambda repository, command, **kwargs: CompletedProcess(command, 0, "not-json", ""),
    )

    with pytest.raises(wt.InfrastructureError, match="invalid Worktrunk JSON"):
        wt.worktrees(tmp_path)


def test_mise_projection_sanitizes_repository_environment(monkeypatch, tmp_path: Path) -> None:
    observed: dict[str, str] = {}

    def fake_run(command: tuple[str, ...], **kwargs: object) -> CompletedProcess[str]:
        environment = kwargs["env"]
        if not isinstance(environment, dict):
            raise TypeError("expected a concrete subprocess environment")
        observed.update(environment)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(wt, "mise_executable", lambda: "/bin/mise")
    monkeypatch.setattr(wt.subprocess, "run", fake_run)
    monkeypatch.setenv("GIT_DIR", "/unsafe")
    monkeypatch.setenv("PYTHONPATH", "/unsafe")

    wt.run_tool(tmp_path, ("uv", "--version"))

    assert "GIT_DIR" not in observed
    assert "PYTHONPATH" not in observed
    assert observed["MISE_TRUSTED_CONFIG_PATHS"] == str(tmp_path.resolve())


def test_worktree_inventory_accepts_only_schema_two_registered_items(
    monkeypatch, tmp_path: Path
) -> None:
    payload = {
        "schema": 2,
        "items": [
            {
                "branch": "impl/member",
                "head": {"sha": "b" * 40},
                "worktree": {
                    "path": str(tmp_path / "member"),
                    "changes": {
                        "staged": False,
                        "modified": True,
                        "untracked": False,
                        "renamed": False,
                        "deleted": False,
                        "conflicted": False,
                    },
                },
            }
        ],
    }
    monkeypatch.setattr(
        wt,
        "run_tool",
        lambda repository, command, **kwargs: CompletedProcess(command, 0, json.dumps(payload), ""),
    )

    assert wt.worktrees(tmp_path) == (
        wt.WorkspaceIdentity(
            branch="impl/member", path=(tmp_path / "member").resolve(), head="b" * 40, dirty=True
        ),
    )
