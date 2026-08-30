"""Behavior tests for the Mise and Worktrunk execution boundary."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

import reposeal.lifecycle as lifecycle


def test_missing_mise_has_an_actionable_noninteractive_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "which", lambda executable: None)

    with pytest.raises(lifecycle.AdmissionError, match="install Mise"):
        lifecycle._run_tool(Path.cwd(), ("uv", "--version"))


def test_invalid_worktrunk_json_is_refused(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        lifecycle,
        "_run_tool",
        lambda repository, command, **kwargs: CompletedProcess(command, 0, "not-json", ""),
    )

    with pytest.raises(lifecycle.AdmissionError, match="invalid Worktrunk JSON"):
        lifecycle._worktrees(tmp_path)


def test_mise_projection_sanitizes_repository_environment(monkeypatch, tmp_path: Path) -> None:
    observed: dict[str, str] = {}

    def fake_run(command: tuple[str, ...], **kwargs: object) -> CompletedProcess[str]:
        environment = kwargs["env"]
        if not isinstance(environment, dict):
            raise TypeError("expected a concrete subprocess environment")
        observed.update(environment)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(lifecycle, "_mise_executable", lambda: "/bin/mise")
    monkeypatch.setattr(lifecycle.subprocess, "run", fake_run)
    monkeypatch.setenv("GIT_DIR", "/unsafe")
    monkeypatch.setenv("PYTHONPATH", "/unsafe")

    lifecycle._run_tool(tmp_path, ("uv", "--version"))

    assert "GIT_DIR" not in observed
    assert "PYTHONPATH" not in observed
    assert observed["MISE_TRUSTED_CONFIG_PATHS"] == str(tmp_path.resolve())


def test_workspace_open_returns_registered_worktrunk_identity(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    created = tmp_path / "repository-feature"
    calls: list[tuple[str, ...]] = []

    def fake_git(repository: Path, *arguments: str, **kwargs: object) -> str:
        responses: dict[tuple[str, ...], str] = {
            ("rev-parse", "--show-toplevel"): str(root),
            ("rev-parse", "base"): "a" * 40,
        }
        return responses[arguments]

    def fake_worktrunk(
        repository: Path, arguments: tuple[str, ...], *, json_output: bool = False
    ) -> object:
        calls.append(arguments)
        if arguments[0] == "switch":
            return {"branch": "feature", "worktree_path": str(created)}
        return {
            "schema": 2,
            "items": [
                {
                    "branch": "feature",
                    "head": {"sha": "a" * 40},
                    "worktree": {
                        "path": str(created),
                        "changes": {
                            "staged": False,
                            "modified": False,
                            "untracked": False,
                            "renamed": False,
                            "deleted": False,
                            "conflicted": False,
                        },
                    },
                }
            ],
        }

    monkeypatch.setattr(lifecycle, "_git", fake_git)
    monkeypatch.setattr(lifecycle, "_worktrunk", fake_worktrunk)

    result = lifecycle.workspace_open(root, "feature", "base")

    assert calls[0] == (
        "switch",
        "--create",
        "feature",
        "--base",
        "base",
        "--no-hooks",
        "--no-cd",
        "--format=json",
    )
    assert result["worktree"] == str(created)
    assert result["source"] == "a" * 40


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
        lifecycle,
        "_run_tool",
        lambda repository, command, **kwargs: CompletedProcess(command, 0, json.dumps(payload), ""),
    )

    assert lifecycle._worktrees(tmp_path) == (
        lifecycle.WorkspaceIdentity(
            branch="impl/member", path=(tmp_path / "member").resolve(), head="b" * 40, dirty=True
        ),
    )


def test_cleanup_retains_dirty_and_advanced_registered_members(monkeypatch, tmp_path: Path) -> None:
    clean = lifecycle.WorkspaceIdentity("clean", tmp_path / "clean", "1" * 40, False)
    dirty = lifecycle.WorkspaceIdentity("dirty", tmp_path / "dirty", "2" * 40, True)
    advanced = lifecycle.WorkspaceIdentity("advanced", tmp_path / "advanced", "3" * 40, False)
    batch = lifecycle.WorkspaceIdentity("batch/test", tmp_path / "batch", "4" * 40, False)
    removals: list[Path] = []
    monkeypatch.setattr(lifecycle, "_worktrees", lambda repository: (clean, dirty, advanced, batch))
    monkeypatch.setattr(
        lifecycle,
        "_remove_workspace",
        lambda repository, workspace: removals.append(workspace.path),
    )

    removed, retained = lifecycle._cleanup_delivered_worktrees(
        tmp_path,
        batch.path,
        [
            {"branch": "clean", "original": "1" * 40},
            {"branch": "dirty", "original": "2" * 40},
            {"branch": "advanced", "original": "0" * 40},
        ],
    )

    assert removed == [str(clean.path), str(batch.path)]
    assert removals == [clean.path, batch.path]
    assert retained == [
        {"branch": "dirty", "worktree": str(dirty.path), "reason": "dirty"},
        {"branch": "advanced", "worktree": str(advanced.path), "reason": "advanced"},
    ]
