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

from signetum.operations import AdmissionError, InfrastructureError, OperationFailed
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


def declared_environment(
    source: Mapping[str, str] | None = None, *, extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Remove repository Git context and a foreign Python environment.

    Engine values reach declared commands only through ``{signetum.*}`` placeholders.
    Mise supplies the tools a project pins; this does not prepend the Skill engine
    environment.
    """

    environment = dict(os.environ if source is None else source)
    for name in tuple(environment):
        if name.startswith("GIT_") or name in {
            "PYTHONHOME",
            "PYTHONPATH",
            "UV_PROJECT_ENVIRONMENT",
            "VIRTUAL_ENV",
        }:
            del environment[name]
    if extra:
        environment.update(extra)
    return environment


def declared_argv(command: tuple[str, ...]) -> tuple[str, ...]:
    """Run a declared argv through Mise without wrapping its exit status."""

    return (mise_executable(), "exec", "--", *command)


# Mise environment configuration files, relative to the project root, by environment name.
_MISE_ENVIRONMENT_FILES = (
    "mise.*.toml",
    ".mise.*.toml",
    "mise/config.*.toml",
    ".mise/config.*.toml",
    ".config/mise.*.toml",
    ".config/mise/config.*.toml",
)
_SELECTED_ENVIRONMENTS: dict[tuple[Path, str], str] = {}


def declared_mise_environments(repository: Path) -> dict[str, tuple[str, ...]]:
    """Mise environments the project declares, each with its configuration files."""

    declared: dict[str, list[str]] = {}
    for pattern in _MISE_ENVIRONMENT_FILES:
        prefix, suffix = pattern.split("*")
        for path in sorted(repository.glob(pattern)):
            relative = path.relative_to(repository).as_posix()
            name = relative.removeprefix(prefix).removesuffix(suffix).removesuffix(".local")
            if name and name != "local" and "." not in name and path.is_file():
                declared.setdefault(name, []).append(relative)
    return {name: tuple(files) for name, files in sorted(declared.items())}


def _provides(repository: Path, tool: str, environment: Mapping[str, str]) -> bool:
    """Whether ``tool`` is executable on the PATH Mise gives commands, system tools included."""
    completed = run_command(
        repository,
        declared_argv(("sh", "-c", 'command -v "$1" >/dev/null', "sh", tool)),
        timeout_seconds=60,
        environment=environment,
    )
    return completed.returncode == 0


def _declared_provider(repository: Path, tool: str, environment: Mapping[str, str]) -> str:
    """The one declared Mise environment providing ``tool``, or a refusal naming them."""

    current = environment.get("MISE_ENV")
    declared = declared_mise_environments(repository)
    providers = (
        ()
        if current
        else tuple(
            name
            for name in declared
            if _provides(repository, tool, {**environment, "MISE_ENV": name})
        )
    )
    if len(providers) == 1:
        return providers[0]
    listing = ", ".join(f"{name} ({', '.join(files)})" for name, files in declared.items())
    if providers:
        advice = "several declared Mise environments provide it: set MISE_ENV to one of " + (
            ", ".join(providers)
        )
    elif declared:
        advice = (
            f"this project declares the Mise environments {listing}; set MISE_ENV to the one "
            f"that declares {tool} and run mise install with it"
        )
    else:
        advice = f"declare {tool} in the project's Mise configuration and run mise install"
    raise InfrastructureError(
        f"{tool} is not available through Mise in {repository} "
        f"(MISE_ENV={current or 'unset'}): {advice}",
        expected=advice,
    )


def run_tool(
    repository: Path,
    command: tuple[str, ...],
    *,
    required: bool = True,
    timeout_seconds: float = 1800,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a declared tool through Mise under the project's declared Mise environment.

    When the tool is not available under the caller's environment and exactly one
    environment the project declares provides it, that environment is used.
    """
    environment = declared_environment(environment)
    key = (repository.resolve(), command[0])
    if "MISE_ENV" not in environment and key in _SELECTED_ENVIRONMENTS:
        environment["MISE_ENV"] = _SELECTED_ENVIRONMENTS[key]
    try:
        unavailable: OSError | None = None
        try:
            completed: subprocess.CompletedProcess[str] | None = run_command(
                repository,
                declared_argv(command),
                timeout_seconds=timeout_seconds,
                environment=environment,
            )
        except OSError as error:
            completed, unavailable = None, error
        if completed is None or completed.returncode != 0:
            if _provides(repository, command[0], environment):
                if unavailable is not None:
                    raise unavailable
            else:
                # The tool never started, so running it under the declared environment is safe.
                selected = _declared_provider(repository, command[0], environment)
                _SELECTED_ENVIRONMENTS[key] = selected
                environment["MISE_ENV"] = selected
                completed = None
        if completed is None:
            completed = run_command(
                repository,
                declared_argv(command),
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
        diagnostic = f"{completed.stdout or ''}{completed.stderr or ''}".strip()
        detail = diagnostic or f"Mise could not execute {command[0]}"
        raise OperationFailed(
            f"declared command failed ({completed.returncode}): {command[0]}\n{detail}",
            expected=(
                "inspect the declared command and retained diagnostics; "
                "repair preparation and retry"
            ),
        )
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
        if branch is None and worktree.get("detached") is True:
            # A detached checkout, such as ready's temporary qualification
            # tree, is not a registered workspace.
            continue
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


def require_removed_workspace(payload: object, workspace: WorkspaceIdentity) -> None:
    """The pinned remove command returns one result per explicitly selected worktree."""
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise InfrastructureError("invalid Worktrunk removal result: expected one worktree result")
    item = payload[0]
    path = item.get("path")
    if (
        item.get("kind") != "worktree"
        or item.get("branch") != workspace.branch
        or not isinstance(path, str)
        or Path(path).resolve() != workspace.path.resolve()
        or item.get("branch_outcome") != "deleted"
    ):
        raise InfrastructureError(
            f"Worktrunk did not confirm removal of the exact workspace: {workspace.branch}",
            expected="inspect retained Worktrunk state before retrying cleanup",
        )
