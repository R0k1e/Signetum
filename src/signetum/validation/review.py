"""Project recovery evidence from exactly the receipts admitted into a batch."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import JsonValue

from signetum.evidence.receipts import EvidenceReceipt, ReceiptError
from signetum.git import GitError, git_output
from signetum.operations import AdmissionError
from signetum.provenance import members_and_plans
from signetum.validation.inheritance import verify_committed_inputs


def recovery_projection(
    receipt: EvidenceReceipt, path: Path, *, member: str | None
) -> list[dict[str, JsonValue]]:
    defects = receipt.extensions.get("recovered_flake_defects", [])
    if not isinstance(defects, list) or any(not isinstance(item, dict) for item in defects):
        raise ReceiptError("invalid recovered robustness defects")
    return [
        {
            **item,
            "source_receipt": str(path),
            "source_gate": receipt.execution.gates[0],
            "source_commit": receipt.identity.commit,
            "member": member,
        }
        for item in defects
        if isinstance(item, dict)
    ]


def member_recovery_review(
    repository: Path, base: str, tip: str, receipt_root: Path
) -> list[dict[str, JsonValue]]:
    if not git_output(repository, "rev-list", "--first-parent", "--merges", f"{base}..{tip}"):
        return []
    members, _ = members_and_plans(repository, base, tip)
    result: list[dict[str, JsonValue]] = []
    for member in members:
        name = member["ready_evidence"]
        if not name or Path(name).name != name:
            raise AdmissionError("admitted member evidence has an invalid receipt path")
        path = receipt_root / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            receipt = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
            if receipt.identity.commit != member["original"] or receipt.execution.gates not in (
                ("member",),
                ("final",),
            ):
                raise ReceiptError("admitted receipt does not bind the original member")
            if match := re.fullmatch(r"(?:member|final)-lifecycle-([0-9a-f]{64})\.json", name):
                if hashlib.sha256(receipt.to_json().encode()).hexdigest() != match[1]:
                    raise ReceiptError("admitted evidence content identity changed")
            verify_committed_inputs(repository, receipt)
            result.extend(recovery_projection(receipt, path, member=member["branch"]))
        except (OSError, ValueError, KeyError, TypeError, GitError) as error:
            raise AdmissionError(
                f"admitted member evidence is unavailable or invalid: {name}: {error}"
            ) from error
    return result
