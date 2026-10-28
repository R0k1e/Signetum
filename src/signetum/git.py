"""The repository-owned Git subprocess boundary for development tooling."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from shutil import which

from signetum.operations import AdmissionError


class GitError(AdmissionError):
    """Git could not establish or change the requested repository state."""


def run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    executable = which("git")
    if executable is None:
        raise GitError("Git executable is unavailable")
    repository_context = {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    }
    environment = {
        name: value for name, value in os.environ.items() if name not in repository_context
    }
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(  # nosec B603 -- resolved Git, explicit argv, no shell
        (executable, "-C", str(repository), *arguments),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def git_output(repository: Path, *arguments: str, check: bool = True, strip: bool = True) -> str:
    completed = run_git(repository, *arguments)
    if check and completed.returncode:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        raise GitError(diagnostic or f"git {' '.join(arguments)} failed")
    return completed.stdout.strip() if strip else completed.stdout
