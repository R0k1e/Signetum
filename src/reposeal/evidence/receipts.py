"""Receipt v2 identities and shard evidence composition."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass


class ReceiptError(ValueError):
    """Evidence cannot prove the requested exact validation."""


_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40,64}")


@dataclass(frozen=True, order=True)
class ArtifactIdentity:
    """One declared configuration or lockfile content identity."""

    path: str
    digest: str

    def __post_init__(self) -> None:
        if not self.path or self.path.startswith("/") or ".." in self.path.split("/"):
            raise ReceiptError(f"artifact path must be repository-relative: {self.path}")
        if _SHA256.fullmatch(self.digest) is None:
            raise ReceiptError(f"artifact digest must be sha256: {self.path}")

    @classmethod
    def from_bytes(cls, path: str, content: bytes) -> ArtifactIdentity:
        return cls(path, "sha256:" + hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, order=True)
class ToolIdentity:
    """Exact identity observed from a declared validation tool."""

    name: str
    identity: str

    def __post_init__(self) -> None:
        if not self.name or not self.identity:
            raise ReceiptError("tool name and identity must be non-empty")


@dataclass(frozen=True)
class EvidenceIdentity:
    """All immutable inputs which make validation evidence reusable."""

    commit: str
    tree: str
    configuration: ArtifactIdentity
    profiles: tuple[str, ...]
    graph: str
    lockfiles: tuple[ArtifactIdentity, ...]
    tools: tuple[ToolIdentity, ...]

    def __post_init__(self) -> None:
        if _COMMIT.fullmatch(self.commit) is None or _COMMIT.fullmatch(self.tree) is None:
            raise ReceiptError("commit and tree must be exact hexadecimal identities")
        if _SHA256.fullmatch(self.graph) is None:
            raise ReceiptError("validation graph digest must be sha256")
        if self.profiles != tuple(sorted(set(self.profiles))):
            raise ReceiptError("profile identities must be unique and sorted")
        if self.lockfiles != tuple(sorted(set(self.lockfiles))):
            raise ReceiptError("lockfile identities must be unique and sorted")
        if self.tools != tuple(sorted(set(self.tools))):
            raise ReceiptError("tool identities must be unique and sorted")

    @property
    def digest(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EvidenceReceipt:
    """Successful evidence for exact shards and any composed named gate."""

    schema_version: int
    identity: EvidenceIdentity
    executed_gates: tuple[str, ...]
    executed_shards: tuple[str, ...]
    valid: bool

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ReceiptError(f"unsupported receipt schema: {self.schema_version}")
        if not self.valid:
            raise ReceiptError("unsuccessful execution is not reusable evidence")
        if self.executed_gates != tuple(sorted(set(self.executed_gates))):
            raise ReceiptError("executed gates must be unique and sorted")
        if self.executed_shards != tuple(sorted(set(self.executed_shards))):
            raise ReceiptError("executed shards must be unique and sorted")

    @classmethod
    def shard(cls, *, identity: EvidenceIdentity, shard: str) -> EvidenceReceipt:
        return cls(2, identity, (), (shard,), True)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    @classmethod
    def from_json(cls, source: str) -> EvidenceReceipt:
        try:
            raw = json.loads(source)
            identity = raw["identity"]
            return cls(
                schema_version=raw["schema_version"],
                identity=EvidenceIdentity(
                    commit=identity["commit"],
                    tree=identity["tree"],
                    configuration=ArtifactIdentity(**identity["configuration"]),
                    profiles=tuple(identity["profiles"]),
                    graph=identity["graph"],
                    lockfiles=tuple(ArtifactIdentity(**item) for item in identity["lockfiles"]),
                    tools=tuple(ToolIdentity(**item) for item in identity["tools"]),
                ),
                executed_gates=tuple(raw["executed_gates"]),
                executed_shards=tuple(raw["executed_shards"]),
                valid=raw["valid"],
            )
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ReceiptError("invalid receipt document") from error


def combine_shard_evidence(
    *, gate: str, required_shards: tuple[str, ...], receipts: tuple[EvidenceReceipt, ...]
) -> EvidenceReceipt:
    """Combine a complete shard set only when every bound identity is exact."""

    if not receipts:
        raise ReceiptError("missing shard evidence")
    identity = receipts[0].identity
    observed: set[str] = set()
    for receipt in receipts:
        if receipt.identity != identity:
            raise ReceiptError("shard evidence identity differs")
        if receipt.executed_gates or len(receipt.executed_shards) != 1:
            raise ReceiptError("only atomic shard evidence can be combined")
        shard = receipt.executed_shards[0]
        if shard in observed:
            raise ReceiptError(f"duplicate shard evidence: {shard}")
        observed.add(shard)
    required = set(required_shards)
    missing = required - observed
    unexpected = observed - required
    if missing:
        raise ReceiptError(f"missing shard evidence: {', '.join(sorted(missing))}")
    if unexpected:
        raise ReceiptError(f"unexpected shard evidence: {', '.join(sorted(unexpected))}")
    return EvidenceReceipt(2, identity, (gate,), tuple(sorted(observed)), True)


def verify_gate_evidence(
    receipt: EvidenceReceipt, *, expected_identity: EvidenceIdentity, gate: str
) -> None:
    """Refuse stale or differently bound evidence at a consuming boundary."""

    if receipt.identity != expected_identity:
        raise ReceiptError("gate evidence identity differs")
    if receipt.executed_gates != (gate,):
        raise ReceiptError(f"receipt does not prove gate: {gate}")


__all__ = [
    "ArtifactIdentity",
    "EvidenceIdentity",
    "EvidenceReceipt",
    "ReceiptError",
    "ToolIdentity",
    "combine_shard_evidence",
    "verify_gate_evidence",
]
