"""Mise-owned Worktrunk execution and registered workspace inventory."""

from __future__ import annotations

import json
import os

# Worktrunk executes through the resolved Mise command without a shell.
import subprocess  # nosec B404
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from signetum.operations import AdmissionError, InfrastructureError
from signetum.validation.process import run_command


@dataclass(frozen=True)
class WorkspaceIdentity:
    """One registered Worktrunk workspace identity."""

    branch: str
    path: Path
    head: str
    dirty: bool


def mise_executable() -> str:
    executable = which("mise")
    if executable is None:
        raise InfrastructureError(
            "Mise executable is unavailable; install Mise and run `mise install` in the repository"
        )
    return executable


def run_tool(
    repository: Path,
    command: tuple[str, ...],
    *,
    required: bool = True,
    timeout_seconds: float = 1800,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ if environment is None else environment)
    for name in tuple(environment):
        if name.startswith("GIT_") or name in {
            "PYTHONHOME",
            "PYTHONPATH",
            "UV_PROJECT_ENVIRONMENT",
            "VIRTUAL_ENV",
        }:
            environment.pop(name)
    environment["MISE_TRUSTED_CONFIG_PATHS"] = str(repository.resolve())
    try:
        completed = run_command(
            repository,
            (mise_executable(), "exec", "--", *command),
            timeout_seconds=timeout_seconds,
            environment=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        if required:
            raise InfrastructureError(
                f"command could not complete: {command[0]}: {error}"
            ) from error
        raise
    if not required:
        return completed
    if completed.returncode != 0:
        diagnostic = (completed.stderr or "").strip() or (completed.stdout or "").strip()
        detail = diagnostic or f"Mise could not execute {command[0]}"
        raise InfrastructureError(f"{detail}; run `mise install` in the repository")
    return completed


def worktrunk(repository: Path, arguments: tuple[str, ...], *, json_output: bool = False) -> object:
    command = (
        "wt",
        "-C",
        str(repository),
        "--yes",
        "--config-set",
        "list.json-schema=2",
        *arguments,
    )
    completed = run_tool(repository, command)
    if not json_output:
        return completed.stdout
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise InfrastructureError(f"invalid Worktrunk JSON: {error.msg}") from error


def worktrees(repository: Path) -> tuple[WorkspaceIdentity, ...]:
    return parse_worktrees(worktrunk(repository, ("list", "--format=json"), json_output=True))


def parse_worktrees(payload: object) -> tuple[WorkspaceIdentity, ...]:
    """Interpret registered workspace identities from the owned schema-two boundary."""
    if not isinstance(payload, dict) or payload.get("schema") != 2:
        raise AdmissionError("invalid Worktrunk JSON: expected schema 2 envelope")
    items = payload.get("items")
    if not isinstance(items, list):
        raise AdmissionError("invalid Worktrunk JSON: items must be a list")
    result: list[WorkspaceIdentity] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("worktree"), dict):
            continue
        branch = item.get("branch")
        head = item.get("head")
        worktree = item["worktree"]
        changes = worktree.get("changes")
        if (
            not isinstance(branch, str)
            or not isinstance(head, dict)
            or not isinstance(head.get("sha"), str)
            or not isinstance(worktree.get("path"), str)
            or not isinstance(changes, dict)
        ):
            raise AdmissionError("invalid Worktrunk JSON: incomplete registered workspace identity")
        dirty = any(
            changes.get(name) is True
            for name in ("staged", "modified", "untracked", "renamed", "deleted", "conflicted")
        )
        result.append(
            WorkspaceIdentity(branch, Path(worktree["path"]).resolve(), head["sha"], dirty)
        )
    return tuple(result)


def registered_workspace(repository: Path, branch: str) -> WorkspaceIdentity:
    matches = tuple(workspace for workspace in worktrees(repository) if workspace.branch == branch)
    if len(matches) != 1:
        raise AdmissionError(f"Worktrunk did not report one registered workspace for {branch}")
    return matches[0]
