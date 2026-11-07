"""Shared command diagnostics and failed-attempt evidence for repository adapters."""

import json
import subprocess  # nosec B404 -- completed-command value only; no execution
import sys
from pathlib import Path

from signetum.serialization import load_json
from signetum.validation.execution import ShardExecution, ValidationExecutionError


def _node_outcomes(path: Path | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read the optional first-attempt node report: ``{"failed": [...], "passed": [...]}``."""
    if path is None or not path.exists():
        return (), ()
    try:
        raw = load_json(path.read_text(encoding="utf-8"))
        if (
            not isinstance(raw, dict)
            or set(raw) != {"failed", "passed"}
            or any(
                not isinstance(raw[key], list)
                or any(not isinstance(node, str) or not node for node in raw[key])
                for key in ("failed", "passed")
            )
        ):
            raise ValueError("invalid node outcome report")
    except (OSError, ValueError) as error:
        raise ValidationExecutionError(f"invalid node report: {error}") from error
    return tuple(raw["failed"]), tuple(raw["passed"])


def read_node_list(path: Path | None) -> tuple[str, ...]:
    """Read a ``{"schema_version": 1, "nodes": [...]}`` file; absent or empty means none."""
    if path is None or not path.exists():
        return ()
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return ()
        raw = load_json(text)
        if (
            not isinstance(raw, dict)
            or set(raw) != {"schema_version", "nodes"}
            or raw["schema_version"] != 1
            or not isinstance(raw["nodes"], list)
            or any(not isinstance(node, str) or not node for node in raw["nodes"])
        ):
            raise ValueError('expected {"schema_version": 1, "nodes": [<node id>, ...]}')
    except (OSError, ValueError) as error:
        raise ValidationExecutionError(f"invalid node list {path.name}: {error}") from error
    return tuple(dict.fromkeys(raw["nodes"]))


def write_node_list(path: Path, nodes: tuple[str, ...]) -> None:
    path.write_text(json.dumps({"schema_version": 1, "nodes": list(nodes)}), encoding="utf-8")


def shard_execution(
    name: str,
    completed: subprocess.CompletedProcess[str],
    report: Path,
    nodes: Path | None = None,
    unreached: Path | None = None,
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
    failed, passed = _node_outcomes(nodes)
    missed = read_node_list(unreached)
    if completed.returncode == 0 and not missed:
        return ShardExecution(True, recovered=recovered, failed_nodes=failed, passed_nodes=passed)
    diagnostic = completed.stdout + completed.stderr
    return ShardExecution(
        False,
        f"{name} exited {completed.returncode}\n{diagnostic}",
        recovered=recovered,
        failed_nodes=failed,
        passed_nodes=passed,
        unreached_nodes=missed,
    )
