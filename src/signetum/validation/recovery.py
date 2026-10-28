"""Shared command results and bounded recovery history for repository adapters."""

import json
import subprocess  # nosec B404 -- completed-command value only; no execution
import sys
from dataclasses import replace
from pathlib import Path

from signetum.evidence.receipts import EvidenceReceipt, ReceiptError
from signetum.validation.execution import ShardExecution, ValidationExecutionError, ValidationInputs


def shard_execution(
    name: str, completed: subprocess.CompletedProcess[str], report: Path
) -> ShardExecution:
    """Preserve command diagnostics and validate all recovered-node evidence."""
    if completed.stdout:
        print(completed.stdout, file=sys.stderr, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    if completed.returncode == 0:
        recovered = ()
        if report.exists():
            try:
                raw = json.loads(report.read_text(encoding="utf-8"))
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
        return ShardExecution(True, recovered=recovered)
    diagnostic = completed.stdout + completed.stderr
    return ShardExecution(False, f"{name} exited {completed.returncode}\n{diagnostic}")


def with_recovery_history(
    inputs: ValidationInputs,
    receipt_root: Path,
    *,
    exclude: Path | None = None,
) -> ValidationInputs:
    """Read the bounded recent successful gate history for member recovery checks."""
    history: list[frozenset[str]] = []
    if inputs.recovery_window == 1:
        return replace(inputs, recovery_history=())
    for path in sorted(
        receipt_root.glob("*.json"), key=lambda candidate: candidate.stat().st_mtime, reverse=True
    ):
        if path == exclude:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            previous = EvidenceReceipt.from_json(source)
            defects = previous.extensions.get("recovered_flake_defects", [])
            if not isinstance(defects, list):
                continue
            history.append(
                frozenset(
                    f"{item['shard']}::{item['node_id']}"
                    for item in defects
                    if isinstance(item, dict)
                    and "shard" in item
                    and "node_id" in item
                    and "inherited_from" not in item
                )
            )
            if len(history) >= inputs.recovery_window - 1:
                break
        except (OSError, ReceiptError, json.JSONDecodeError):
            continue
    return replace(inputs, recovery_history=tuple(history))
