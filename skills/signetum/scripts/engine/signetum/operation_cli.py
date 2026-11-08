"""Portable lifecycle CLI refusal, result and retained-diagnostic authority."""

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Never

from signetum.git import GitError
from signetum.manifest import ManifestError, UnsupportedManifestError
from signetum.operations import (
    EXIT_CODES,
    AdmissionError,
    OperationError,
    OperationResult,
    OperationStatus,
)
from signetum.profiles.catalog import ProfileError, ProfileResourceError
from signetum.validation import ValidationGraphError
from signetum.validation.execution import ValidationExecutionError, ValidationInfrastructureError
from signetum.workspaces import WorkspaceError


class OperationParser(argparse.ArgumentParser):
    """Keep invalid lifecycle invocations in the result contract."""

    def error(self, message: str) -> Never:
        raise AdmissionError(message, expected=f"inspect {self.prog} --help and correct arguments")


def run_operation(
    repository: Path,
    operation: str,
    action: Callable[[], dict[str, object]],
    *,
    state_root: Callable[[Path], Path],
) -> int:
    """Render one result while preserving the operation's actual failure category."""
    try:
        result = action()
    except (
        OperationError,
        ManifestError,
        ProfileError,
        ValidationGraphError,
        ValidationExecutionError,
        WorkspaceError,
        GitError,
        OSError,
    ) as error:
        status, expected = _error_category(error)
        log = _archive_operation_failure(repository, str(error), state_root)
        print(f"{operation}: {str(error)[-2000:]}", file=sys.stderr)
        failure = OperationResult(
            operation, status, _node_fields(error), str(error)[-2000:], expected, log
        )
        print(json.dumps(failure.document(), sort_keys=True))
        return EXIT_CODES[status]
    outcome = result.pop("status", "passed")
    document = OperationResult(
        operation, OperationStatus.PASSED, {**result, "outcome": outcome}
    ).document()
    print(json.dumps(document, sort_keys=True))
    return 0


def _node_fields(error: Exception) -> dict[str, object]:
    """First-attempt failed nodes, listed whole even when the diagnostic is truncated."""
    if not isinstance(error, ValidationExecutionError) or not (
        error.failed_nodes or error.unreached_nodes
    ):
        return {}
    recovered = set(error.recovered_nodes)
    return {
        "first_attempt_failures": [
            {"shard": shard, "node_id": node, "passed_on_retry": (shard, node) in recovered}
            for shard, node in error.failed_nodes
        ],
        "unreached_nodes": [
            {"shard": shard, "node_id": node} for shard, node in error.unreached_nodes
        ],
    }


def _archive_operation_failure(
    repository: Path, diagnostic: str, state_root: Callable[[Path], Path]
) -> str | None:
    """Retain failure output under the shared machine-local state authority."""

    try:
        root = state_root(repository) / "logs"
        root.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="operation-", suffix=".log", dir=root)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(diagnostic + "\n")
        return name
    except (OSError, OperationError):
        return None


def utility_failure(operation: str, error: Exception, **fields: object) -> int:
    """Use the same result/exit contract for utilities without another runner."""
    status, expected = _error_category(error)
    from signetum.workspaces import state_root  # noqa: PLC0415 -- avoid owner cycle

    log = _archive_operation_failure(Path.cwd(), str(error), state_root)
    result = OperationResult(
        operation,
        status,
        {"state_change": "not_confirmed", **fields},
        str(error)[-2000:],
        expected,
        log,
    )
    print(f"{operation}: {str(error)[-2000:]}", file=sys.stderr)
    print(json.dumps(result.document(), sort_keys=True))
    return EXIT_CODES[status]


def _error_category(error: Exception) -> tuple[OperationStatus, str]:
    if isinstance(error, OperationError):
        return error.status, error.expected
    if isinstance(error, UnsupportedManifestError):
        # A member's engine or schema change admitted into a batch makes the
        # batch manifest newer than the engines of its siblings and main; an
        # engine update makes the delivered manifest older than the engine.
        return (
            OperationStatus.INVALID,
            "This engine and the manifest it read disagree on its format. A manifest newer "
            "than this engine needs the engine it names: for a batch, run from the batch "
            "workspace when the repository runs its own engine, otherwise update the Skill. "
            "Ready members whose evidence an older engine produced stay admissible without "
            "rerunning their checks. A manifest older than this engine is migrated in a "
            "member: workspace-open and status read an older manifest, and batch-open and "
            "batch-admit read only the locations of an older batch manifest, so that member "
            "can be opened and admitted. ready, final and journal writes need the format this "
            "engine reads; a member still holding the older manifest takes a delivered "
            "migration with maintenance workspace-sync or migrates it itself.",
        )
    if isinstance(error, (ValidationInfrastructureError, ProfileResourceError, OSError)):
        return (
            OperationStatus.INFRASTRUCTURE_ERROR,
            "Restore the declared inputs and tools, inspect status, then retry.",
        )
    if isinstance(error, ValidationExecutionError):
        return OperationStatus.FAILED, "Repair the failing checks and retry ordinary validation."
    return OperationStatus.INVALID, "Correct the input, inspect retained state and retry."
