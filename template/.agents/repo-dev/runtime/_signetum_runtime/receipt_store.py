# Generated from signetum.validation.receipt_store; edit the engine source and regenerate.
"""Content-addressed successful validation evidence outside the source tree."""

import hashlib
from pathlib import Path

from .evidence_receipts import (
    EvidenceIdentity,
    EvidenceReceipt,
    ReceiptError,
    verify_gate_evidence,
)


class ReceiptStore:
    """Content-addressed successful evidence outside the repository tree."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def write(self, gate: str, receipt: EvidenceReceipt) -> Path:
        encoded = receipt.to_json()
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / f"{gate}-{digest}.json"
        destination.write_text(encoded, encoding="utf-8")
        return destination

    def matching(
        self,
        gate: str,
        identity: EvidenceIdentity,
        required_digests: frozenset[str],
    ) -> Path:
        """Locate evidence binding this identity and proving these commands.

        Evidence is never matched by whole-document equality. A world shard
        records when it observed the world, so two honest runs of one gate are
        never byte-identical.
        """

        for path in sorted(self.root.glob(f"{gate}-*.json")):
            try:
                observed = EvidenceReceipt.from_json(path.read_text(encoding="utf-8"))
                verify_gate_evidence(observed, expected_identity=identity, gate=gate)
            except (OSError, UnicodeError, ReceiptError):
                continue
            if required_digests <= observed.execution.command_digests:
                return path
        raise ReceiptError(f"no {gate} receipt proves the required commands")
