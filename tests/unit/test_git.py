"""Explicit repository scope and transport settings survive the shared Git boundary."""

import subprocess
from pathlib import Path

from signetum import git


def test_git_uses_the_requested_repository_despite_inherited_context(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    assert git.run_git(repository, "init").returncode == 0
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "different.git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "different-index"))
    observed = git.git_output(repository, "rev-parse", "--show-toplevel")
    assert Path(observed).resolve() == repository.resolve()


def test_git_retains_transport_configuration_without_interactive_prompts(tmp_path, monkeypatch):
    environment = {}

    def run(command, **kwargs):
        environment.update(kwargs["env"])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("GIT_SSH_COMMAND", "fixture-ssh")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")
    monkeypatch.setattr(git.subprocess, "run", run)
    git.run_git(tmp_path, "ls-remote", "origin")
    assert environment["GIT_SSH_COMMAND"] == "fixture-ssh"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
