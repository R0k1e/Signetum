"""Receipt v2 identities and shard evidence composition."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from pydantic import JsonValue


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
    base: str | None
    configuration: ArtifactIdentity
    profiles: tuple[str, ...]
    graph: str
    lockfiles: tuple[ArtifactIdentity, ...]
    tools: tuple[ToolIdentity, ...]

    def __post_init__(self) -> None:
        if _COMMIT.fullmatch(self.commit) is None or _COMMIT.fullmatch(self.tree) is None:
            raise ReceiptError("commit and tree must be exact hexadecimal identities")
        if self.base is not None and _COMMIT.fullmatch(self.base) is None:
            raise ReceiptError("base must be an exact hexadecimal identity")
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
class ValidationSelection:
    changed_paths_digest: str
    rules: tuple[str, ...]
    profiles: tuple[str, ...]
    gates: tuple[str, ...]
    shards: tuple[str, ...]
    modified_tests: tuple[str, ...]
    external_obligations: tuple[str, ...]
    unexplained: tuple[str, ...]
    requires_final: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.changed_paths_digest) is None:
            raise ReceiptError("changed paths digest must be sha256")
        for field in (
            self.rules,
            self.profiles,
            self.gates,
            self.shards,
            self.modified_tests,
            self.external_obligations,
            self.unexplained,
            self.reasons,
        ):
            if len(field) != len(set(field)):
                raise ReceiptError("selection values must be unique")


@dataclass(frozen=True)
class ValidationExecution:
    gates: tuple[str, ...]
    shards: tuple[str, ...]
    external_obligations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationCompleteness:
    member: bool
    final: bool
    required_shards: tuple[str, ...]


@dataclass(frozen=True)
class ValidationProvenance:
    stable_patch_id: str | None = None

    def __post_init__(self) -> None:
        if self.stable_patch_id is not None and _COMMIT.fullmatch(self.stable_patch_id) is None:
            raise ReceiptError("stable patch id must be hexadecimal")


@dataclass(frozen=True)
class EvidenceReceipt:
    """Successful evidence for exact shards and any composed named gate."""

    schema_version: int
    protocol: str
    schema_digest: str
    identity: EvidenceIdentity
    selection: ValidationSelection | None
    execution: ValidationExecution
    completeness: ValidationCompleteness
    provenance: ValidationProvenance
    extensions: dict[str, JsonValue]
    valid: bool

    def __post_init__(self) -> None:
        if self.schema_version != 3:
            raise ReceiptError(f"unsupported receipt schema: {self.schema_version}")
        if self.protocol != "reposeal.validation-evidence@3":
            raise ReceiptError(f"unsupported evidence protocol: {self.protocol}")
        if _SHA256.fullmatch(self.schema_digest) is None:
            raise ReceiptError("schema digest must be sha256")
        if not self.valid:
            raise ReceiptError("unsuccessful execution is not reusable evidence")
        if self.execution.gates != tuple(sorted(set(self.execution.gates))):
            raise ReceiptError("executed gates must be unique and sorted")
        if self.execution.shards != tuple(sorted(set(self.execution.shards))):
            raise ReceiptError("executed shards must be unique and sorted")

    @classmethod
    def shard(
        cls,
        *,
        identity: EvidenceIdentity,
        shard: str,
        protocol: str,
        schema_digest: str,
        selection: ValidationSelection | None,
    ) -> EvidenceReceipt:
        return cls(
            3,
            protocol,
            schema_digest,
            identity,
            selection,
            ValidationExecution((), (shard,)),
            ValidationCompleteness(False, False, (shard,)),
            ValidationProvenance(),
            {},
            True,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    @classmethod
    def from_json(cls, source: str) -> EvidenceReceipt:
        try:
            raw = json.loads(source)
            identity = raw["identity"]
            return cls(
                schema_version=raw["schema_version"],
                protocol=raw["protocol"],
                schema_digest=raw["schema_digest"],
                identity=EvidenceIdentity(
                    commit=identity["commit"],
                    tree=identity["tree"],
                    base=identity["base"],
                    configuration=ArtifactIdentity(**identity["configuration"]),
                    profiles=tuple(identity["profiles"]),
                    graph=identity["graph"],
                    lockfiles=tuple(ArtifactIdentity(**item) for item in identity["lockfiles"]),
                    tools=tuple(ToolIdentity(**item) for item in identity["tools"]),
                ),
                selection=(
                    ValidationSelection(
                        changed_paths_digest=raw["selection"]["changed_paths_digest"],
                        rules=tuple(raw["selection"]["rules"]),
                        profiles=tuple(raw["selection"]["profiles"]),
                        gates=tuple(raw["selection"]["gates"]),
                        shards=tuple(raw["selection"]["shards"]),
                        modified_tests=tuple(raw["selection"]["modified_tests"]),
                        external_obligations=tuple(raw["selection"]["external_obligations"]),
                        unexplained=tuple(raw["selection"]["unexplained"]),
                        requires_final=raw["selection"]["requires_final"],
                        reasons=tuple(raw["selection"]["reasons"]),
                    )
                    if raw["selection"] is not None
                    else None
                ),
                execution=ValidationExecution(
                    gates=tuple(raw["execution"]["gates"]),
                    shards=tuple(raw["execution"]["shards"]),
                    external_obligations=tuple(raw["execution"]["external_obligations"]),
                ),
                completeness=ValidationCompleteness(
                    member=raw["completeness"]["member"],
                    final=raw["completeness"]["final"],
                    required_shards=tuple(raw["completeness"]["required_shards"]),
                ),
                provenance=ValidationProvenance(**raw["provenance"]),
                extensions=raw["extensions"],
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
        if receipt.execution.gates or len(receipt.execution.shards) != 1:
            raise ReceiptError("only atomic shard evidence can be combined")
        shard = receipt.execution.shards[0]
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
    first = receipts[0]
    return EvidenceReceipt(
        3,
        first.protocol,
        first.schema_digest,
        identity,
        first.selection,
        ValidationExecution((gate,), tuple(sorted(observed))),
        ValidationCompleteness(gate == "member", gate == "final", tuple(sorted(required))),
        first.provenance,
        first.extensions,
        True,
    )


def verify_gate_evidence(
    receipt: EvidenceReceipt, *, expected_identity: EvidenceIdentity, gate: str
) -> None:
    """Refuse stale or differently bound evidence at a consuming boundary."""

    if receipt.identity != expected_identity:
        raise ReceiptError("gate evidence identity differs")
    if receipt.execution.gates != (gate,):
        raise ReceiptError(f"receipt does not prove gate: {gate}")


__all__ = [
    "ArtifactIdentity",
    "EvidenceIdentity",
    "EvidenceReceipt",
    "ReceiptError",
    "ToolIdentity",
    "ValidationCompleteness",
    "ValidationExecution",
    "ValidationProvenance",
    "ValidationSelection",
    "combine_shard_evidence",
    "verify_gate_evidence",
]
