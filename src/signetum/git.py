"""The repository-owned Git subprocess boundary for development tooling."""

from __future__ import annotations

import os

# Git uses a resolved executable, explicit argv and no shell.
import subprocess  # nosec B404
from collections.abc import Mapping
from pathlib import Path
from shutil import which

from signetum.operations import AdmissionError, OperationStatus


class GitError(AdmissionError):
    """Git could not establish or change the requested repository state."""


class GitInfrastructureError(GitError):
    """Git is unavailable, without changing ordinary Git refusal semantics."""

    status = OperationStatus.INFRASTRUCTURE_ERROR


def isolated_git_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Do not let inherited Git context redirect a command's declared repository."""
    repository_context = {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    }
    environment = {
        name: value
        for name, value in (source if source is not None else os.environ).items()
        if name not in repository_context
    }
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    executable = which("git")
    if executable is None:
        raise GitInfrastructureError(
            "Git executable is unavailable", expected="restore the Git executable and retry"
        )
    return subprocess.run(  # noqa: S603  # nosec B603 -- resolved Git, explicit argv, no shell
        (executable, "-C", str(repository), *arguments),
        check=False,
        capture_output=True,
        text=True,
        env=isolated_git_environment(),
    )


def git_output(repository: Path, *arguments: str, check: bool = True, strip: bool = True) -> str:
    completed = run_git(repository, *arguments)
    if check and completed.returncode:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        raise GitError(diagnostic or f"git {' '.join(arguments)} failed")
    return completed.stdout.strip() if strip else completed.stdout
