# Generated from signetum.validation.recovery; edit the engine source and regenerate.
"""Shared command diagnostics and failed-attempt evidence for repository adapters."""

import subprocess  # nosec B404 -- completed-command value only; no execution
import sys
from pathlib import Path

from .execution import ShardExecution, ValidationExecutionError
from .serialization import load_json


def shard_execution(
    name: str, completed: subprocess.CompletedProcess[str], report: Path
) -> ShardExecution:
    """Preserve command diagnostics and validate all recovered-node evidence."""
    if completed.stdout:
        print(completed.stdout, file=sys.stderr, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    recovered = ()
    if report.exists():
        try:
            raw = load_json(report.read_text(encoding="utf-8"))
            if not isinstance(raw, list) or any(
                not isinstance(item, dict)
                or not isinstance(item.get("node_id"), str)
                or not item.get("node_id")
                or not isinstance(item.get("first_failure"), list)
                or not any(
                    isinstance(phase, dict) and phase.get("outcome") == "failed"
                    for phase in item["first_failure"]
                )
                for item in raw
            ):
                raise ValueError("invalid recovered-node evidence")
            recovered = tuple(raw)
        except (OSError, ValueError) as error:
            raise ValidationExecutionError(f"invalid recovery report: {error}") from error
    if completed.returncode == 0:
        return ShardExecution(True, recovered=recovered)
    diagnostic = completed.stdout + completed.stderr
    return ShardExecution(
        False, f"{name} exited {completed.returncode}\n{diagnostic}", recovered=recovered
    )
