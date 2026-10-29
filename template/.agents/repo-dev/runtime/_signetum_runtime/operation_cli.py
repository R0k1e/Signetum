# Generated from signetum.operation_cli; edit the engine source and regenerate.
"""Portable lifecycle CLI refusal, result and retained-diagnostic authority."""

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Never

from .execution import ValidationExecutionError, ValidationInfrastructureError
from .git import GitError
from .manifest import ManifestError
from .operations import (
    EXIT_CODES,
    AdmissionError,
    OperationError,
    OperationResult,
    OperationStatus,
)
from .profile_catalog import ProfileError, ProfileResourceError
from .validation import ValidationGraphError
from .workspaces import WorkspaceError


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
        if isinstance(error, OperationError):
            status = error.status
            expected = error.expected
        elif isinstance(error, (ValidationInfrastructureError, ProfileResourceError)):
            status = OperationStatus.INFRASTRUCTURE_ERROR
            expected = "restore the declared validation inputs and tools, then retry"
        elif isinstance(error, ValidationExecutionError):
            status = OperationStatus.FAILED
            expected = "repair the failing checks and retry the operation"
        elif isinstance(error, OSError):
            status = OperationStatus.INFRASTRUCTURE_ERROR
            expected = "restore the required executable or filesystem and retry"
        else:
            status = OperationStatus.INVALID
            expected = "correct the repository manifest and retry"
        log = _archive_operation_failure(repository, str(error), state_root)
        print(f"{operation}: {error}", file=sys.stderr)
        failure = OperationResult(operation, status, {}, str(error), expected, log)
        print(json.dumps(failure.document(), sort_keys=True))
        return EXIT_CODES[status]
    outcome = result.pop("status", "passed")
    document = OperationResult(
        operation, OperationStatus.PASSED, {**result, "outcome": outcome}
    ).document()
    print(json.dumps(document, sort_keys=True))
    return 0


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
