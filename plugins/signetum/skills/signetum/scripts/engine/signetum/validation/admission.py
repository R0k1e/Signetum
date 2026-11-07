"""One exact-input tree-evidence verdict for member admission."""

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from signetum.evidence.receipts import (
    EvidenceIdentity,
    EvidenceReceipt,
    ReceiptError,
    ValidationSelection,
)
from signetum.operations import AdmissionError
from signetum.serialization import ValueDecodeError, load_json
from signetum.validation.configuration import ENGINE_TOOL
from signetum.validation.execution import ValidationInputs, require_original_success


def _observed_environment(receipt: EvidenceReceipt, expected: Mapping[str, str]) -> bool:
    """Every shard this member run executed saw the current member bases."""

    details = receipt.extensions.get("shard_details", {})
    inherited = receipt.extensions.get("inherited_test_evidence_from", {})
    reused = inherited.get("shards", []) if isinstance(inherited, dict) else []
    if not isinstance(details, dict) or not isinstance(reused, list):
        return False
    for outcome in receipt.execution.shards:
        if outcome.name in reused:
            continue
        detail = details.get(outcome.name)
        if not isinstance(detail, dict) or detail.get("environment") != dict(expected):
            return False
    return True


def _checked_inputs(identity: EvidenceIdentity) -> EvidenceIdentity:
    """The member's own inputs, without the engine that judged them.

    A sibling's engine or manifest-schema change makes the admitting engine
    differ from the one that ran ready. The member's tree, configuration,
    lockfiles and declared tools stay bound exactly, and the batch gate then
    checks the merged result with the admitting engine.
    """

    return replace(
        identity, tools=tuple(tool for tool in identity.tools if tool.name != ENGINE_TOOL)
    )


def find_member_evidence(
    receipt_root: Path,
    *,
    tip: str,
    schema_digest: str,
    member_identity: EvidenceIdentity,
    final_graph_digest: str,
    required_digests: frozenset[str],
    member_environment: Mapping[str, str],
    inputs: ValidationInputs,
    expected_selection: ValidationSelection | None = None,
    final_required_digests: frozenset[str] | None = None,
) -> str:
    """Require exact identity, complete tree checks and current qualification."""
    expected = {
        "member": member_identity,
        "final": replace(member_identity, graph=final_graph_digest),
    }
    for path in sorted(receipt_root.glob("*-lifecycle-*.json")):
        try:
            payload = load_json(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            receipt = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueDecodeError,
            ReceiptError,
        ):
            continue
        if not receipt.valid or receipt.schema_digest != schema_digest:
            continue
        if len(receipt.execution.gates) != 1:
            continue
        identity = expected.get(receipt.execution.gates[0])
        if (
            identity is None
            or identity.commit != tip
            or _checked_inputs(receipt.identity) != _checked_inputs(identity)
        ):
            continue
        if (
            receipt.execution.gates == ("member",)
            and expected_selection is not None
            and receipt.selection != expected_selection
        ):
            continue
        if receipt.execution.gates == ("member",) and not _observed_environment(
            receipt, member_environment
        ):
            continue
        proven = frozenset(
            outcome.command_digest
            for outcome in receipt.execution.shards
            if outcome.evidence == "tree" and outcome.status == "passed"
        )
        needed = (
            final_required_digests
            if receipt.execution.gates == ("final",) and final_required_digests is not None
            else required_digests
        )
        if needed <= proven:
            require_original_success(receipt.extensions.get("recovered_flake_defects", []))
            return path.name
    raise AdmissionError(
        "member has no evidence proving its selected validation for the exact tip and inputs"
    )
