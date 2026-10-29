# Generated from signetum.git; edit the engine source and regenerate.
"""The repository-owned Git subprocess boundary for development tooling."""

from __future__ import annotations

import os
import re

# Git uses a resolved executable, explicit argv and no shell.
import subprocess  # nosec B404
from collections.abc import Mapping
from pathlib import Path
from shutil import which

from .operations import AdmissionError, OperationStatus


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


def read_blob_contents(repository: Path, identities: tuple[str, ...]) -> dict[str, bytes]:
    """Read exact immutable blobs in one Git process, including non-UTF8 source."""
    if any(re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", value) is None for value in identities):
        raise GitError("blob reads require exact Git object identities")
    if not identities:
        return {}
    executable = which("git")
    if executable is None:
        raise GitInfrastructureError("Git executable is unavailable")
    result = subprocess.run(  # noqa: S603  # nosec B603 -- exact object identities, no shell
        (executable, "-C", str(repository), "cat-file", "--batch"),
        input=("\n".join(identities) + "\n").encode(),
        capture_output=True,
        check=False,
        env=isolated_git_environment(),
    )
    if result.returncode:
        raise GitError("committed blob inventory is unavailable")
    offset = 0
    blobs = {}
    for identity in identities:
        end = result.stdout.index(b"\n", offset)
        header = result.stdout[offset:end].decode().split()
        if len(header) != 3 or header[:2] != [identity, "blob"]:
            raise GitError("unexpected committed blob response")
        length = int(header[2])
        start = end + 1
        blobs[identity] = result.stdout[start : start + length]
        if result.stdout[start + length : start + length + 1] != b"\n":
            raise GitError("incomplete committed blob response")
        offset = start + length + 1
    if offset != len(result.stdout):
        raise GitError("unexpected trailing blob data")
    return blobs


def regular_tree_files(repository: Path, source: str) -> dict[str, str]:
    """One regular-file inventory from the exact committed tree."""
    result = {}
    for entry in git_output(repository, "ls-tree", "-r", "-z", source, strip=False).split("\0"):
        if not entry:
            continue
        header, path = entry.split("\t", 1)
        mode, kind, identity = header.split()
        if kind == "blob" and mode in {"100644", "100755"}:
            result[path] = identity
    return result
