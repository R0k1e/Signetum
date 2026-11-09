"""Shared command diagnostics and failed-attempt evidence for repository adapters."""

import json
import subprocess  # nosec B404 -- completed-command value only; no execution
import sys
from pathlib import Path

from signetum.serialization import load_json
from signetum.validation.execution import ShardExecution, ValidationExecutionError


def node_outcomes(
    path: Path | None,
) -> tuple[
    tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...] | None
]:
    """Read the optional first-attempt node report.

    ``{"failed": [...], "passed": [...], "unreached": [...], "failed_checks": [...]}``;
    ``unreached``, ``failed_checks`` and ``not_collected`` are optional. Returns
    failed, passed, unreached, failed checks and absent nodes; None distinguishes
    a legacy runner from one explicitly reporting an empty collection difference.
    """
    optional = {"unreached", "failed_checks", "not_collected"}
    if path is None or not path.exists():
        return (), (), (), (), None
    try:
        raw = load_json(path.read_text(encoding="utf-8"))
        if (
            not isinstance(raw, dict)
            or not {"failed", "passed"} <= set(raw) <= {"failed", "passed", *optional}
            or any(
                not isinstance(value, list)
                or any(not isinstance(node, str) or not node for node in value)
                for value in raw.values()
            )
        ):
            raise ValueError("invalid node outcome report")
    except (OSError, ValueError) as error:
        raise ValidationExecutionError(f"invalid node report: {error}") from error
    return (
        tuple(raw["failed"]),
        tuple(raw["passed"]),
        tuple(raw.get("unreached", ())),
        tuple(raw.get("failed_checks", ())),
        tuple(raw["not_collected"]) if "not_collected" in raw else None,
    )


def write_node_list(path: Path, nodes: tuple[str, ...]) -> None:
    path.write_text(json.dumps({"schema_version": 1, "nodes": list(nodes)}), encoding="utf-8")


def shard_execution(
    name: str,
    completed: subprocess.CompletedProcess[str],
    report: Path,
    nodes: Path | None = None,
) -> ShardExecution:
    """Preserve command diagnostics and validate recovered-node and node-outcome evidence."""
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
    failed, passed, missed, checks, absent = node_outcomes(nodes)
    if completed.returncode == 0 and not missed:
        return ShardExecution(
            True,
            recovered=recovered,
            failed_nodes=failed,
            passed_nodes=passed,
            exit_code=0,
            failed_checks=checks,
            not_collected=absent,
        )
    diagnostic = completed.stdout + completed.stderr
    return ShardExecution(
        False,
        f"{name} exited {completed.returncode}\n{diagnostic}",
        recovered=recovered,
        failed_nodes=failed,
        passed_nodes=passed,
        unreached_nodes=missed,
        exit_code=completed.returncode,
        failed_checks=checks,
        not_collected=absent,
    )
