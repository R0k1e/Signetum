"""Guarded preparation execution without readiness or delivery evidence."""

import subprocess  # nosec B404 -- completed-command type only
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypedDict

from signetum.git import git_output, run_git
from signetum.operations import AdmissionError, OperationFailed
from signetum.validation import ValidationGraph
from signetum.workspaces import require_clean


class PreparationResult(TypedDict):
    status: str
    worktree: str
    executed: list[str]


class PreparationRunner(Protocol):
    def __call__(
        self, repository: Path, command: tuple[str, ...], *, timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        """Run one declared preparation command or raise an infrastructure failure."""


def prepare_workspace(
    repository: Path,
    resolve_graph: Callable[[], ValidationGraph],
    runner: PreparationRunner,
    *,
    allow_merge: bool = False,
) -> PreparationResult:
    """Prepare only a clean tree or fully staged merge, preserving source identity."""
    index_tree = None
    if allow_merge:
        index_tree = git_output(repository, "write-tree")
        if run_git(repository, "diff", "--quiet").returncode or git_output(
            repository, "ls-files", "--others", "--exclude-standard"
        ):
            raise AdmissionError("preparation requires all merge resolutions staged")
    else:
        require_clean(repository)
    before = git_output(repository, "rev-parse", "HEAD")
    graph = resolve_graph()
    if not any(gate.name == "prepare" for gate in graph.gates):
        raise AdmissionError("declare a prepare gate before preparing this workspace")
    by_name = {shard.name: shard for shard in graph.shards}
    executed: list[str] = []
    for name in graph.execution_order("prepare"):
        shard = by_name[name]
        completed = runner(repository, shard.command, timeout_seconds=shard.timeout_seconds)
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        executed.append(name)
    if allow_merge:
        if (
            git_output(repository, "write-tree") != index_tree
            or run_git(repository, "diff", "--quiet").returncode
        ):
            raise OperationFailed("preparation changed the staged merge")
    else:
        require_clean(repository)
    if git_output(repository, "rev-parse", "HEAD") != before:
        raise OperationFailed("preparation changed the committed source identity")
    return {"status": "prepared", "worktree": str(repository), "executed": executed}
