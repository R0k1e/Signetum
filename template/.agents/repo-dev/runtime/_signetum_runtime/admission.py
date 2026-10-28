# Generated from signetum.validation.admission; edit the engine source and regenerate.
"""One exact-input tree-evidence verdict for member admission."""

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from .evidence_receipts import EvidenceIdentity, EvidenceReceipt, ReceiptError
from .execution import ValidationInputs, require_recovery_limit
from .operations import AdmissionError
from .recovery import with_recovery_history


def find_member_evidence(
    receipt_root: Path,
    *,
    tip: str,
    schema_digest: str,
    member_identity: EvidenceIdentity,
    final_graph_digest: str,
    required_digests: frozenset[str],
    ratchet_baselines: Mapping[str, str],
    inputs: ValidationInputs,
) -> str:
    """Require exact identity, complete tree checks and current qualification."""
    expected = {
        "member": member_identity,
        "final": replace(member_identity, graph=final_graph_digest),
    }
    for path in sorted(receipt_root.glob("*-lifecycle-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            receipt = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ReceiptError):
            continue
        if not receipt.valid or receipt.schema_digest != schema_digest:
            continue
        if len(receipt.execution.gates) != 1:
            continue
        identity = expected.get(receipt.execution.gates[0])
        if identity is None or identity.commit != tip or receipt.identity != identity:
            continue
        if receipt.execution.gates == ("member",) and ratchet_baselines:
            details = receipt.extensions.get("shard_details", {})
            if not isinstance(details, dict):
                continue
            qualified = True
            for name, qualified_base in ratchet_baselines.items():
                detail = details.get(name)
                report = detail.get("ratchet") if isinstance(detail, dict) else None
                if not isinstance(report, dict) or report.get("baseline") != qualified_base:
                    qualified = False
                    break
            if not qualified:
                continue
        proven = frozenset(
            outcome.command_digest
            for outcome in receipt.execution.shards
            if outcome.evidence == "tree" and outcome.status == "passed"
        )
        if required_digests <= proven:
            if receipt.execution.gates == ("final",):
                policy_inputs = with_recovery_history(
                    inputs,
                    receipt_root,
                    exclude=path.with_name(path.name.replace("-lifecycle-", "-")),
                )
                require_recovery_limit(
                    receipt.extensions.get("recovered_flake_defects", []), policy_inputs
                )
            return path.name
    raise AdmissionError(
        "member has no evidence proving its selected validation for the exact tip and inputs"
    )
