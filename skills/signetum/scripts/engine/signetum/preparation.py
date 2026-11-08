"""Guarded preparation execution without readiness or delivery evidence."""

import json
import shlex
import subprocess  # nosec B404 -- completed-command type only
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypedDict

from signetum.git import git_output, run_git
from signetum.operations import AdmissionError, OperationError, OperationFailed
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


def _adapter_expected(output: str) -> str | None:
    """The expected action a repository adapter printed as one JSON result line."""
    for line in reversed(output.splitlines()):
        try:
            document = json.loads(line)
        except ValueError:
            continue
        if isinstance(document, dict) and isinstance(document.get("expected"), str):
            return f"the preparation adapter expects: {document['expected']}"
    return None


def prepare_workspace(
    repository: Path,
    resolve_graph: Callable[[], ValidationGraph],
    runner: PreparationRunner,
    *,
    allow_merge: bool = False,
) -> PreparationResult:
    """Prepare only a clean tree or fully staged merge, preserving source identity.

    A prepare shard may rebuild ignored or derived state, such as a stale
    environment; preparation continues when it exits zero and the tracked source
    and index are unchanged.
    """
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
        try:
            completed = runner(repository, shard.command, timeout_seconds=shard.timeout_seconds)
        except OperationError as error:
            raise type(error)(
                f"preparation shard {name} failed: {shlex.join(shard.command)}\n{error}",
                expected=_adapter_expected(str(error))
                or (
                    f"run the declared command {shlex.join(shard.command)} in {repository} to "
                    "rebuild or repair the prepared state, then retry"
                ),
            ) from error
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
