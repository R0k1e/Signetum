from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256

import pytest

from reposeal.evidence.receipts import (
    ArtifactIdentity,
    EvidenceIdentity,
    EvidenceReceipt,
    ReceiptError,
    ShardOutcome,
    ToolIdentity,
    ValidationCompleteness,
    ValidationExecution,
    ValidationProvenance,
    combine_shard_evidence,
    verify_gate_evidence,
)
from reposeal.resources.schemas import evidence_schema_digest


def _identity() -> EvidenceIdentity:
    return EvidenceIdentity(
        commit="a" * 40,
        tree="b" * 40,
        base="f" * 40,
        configuration=ArtifactIdentity("reposeal.toml", "sha256:" + "c" * 64),
        profiles=("python-default@2",),
        graph="sha256:" + "d" * 64,
        lockfiles=(ArtifactIdentity("uv.lock", "sha256:" + "e" * 64),),
        tools=(ToolIdentity("ruff", "0.12.9"), ToolIdentity("uv", "0.8.14")),
    )


def _outcome(name: str) -> ShardOutcome:
    digest = "sha256:" + sha256(name.encode()).hexdigest()
    return ShardOutcome(name, digest, "tree", "passed")


def _shard(identity: EvidenceIdentity, name: str) -> EvidenceReceipt:
    return EvidenceReceipt.shard(
        identity=identity,
        shard=_outcome(name),
        protocol="reposeal.validation-evidence@3",
        schema_digest="sha256:" + "9" * 64,
        selection=None,
    )


def _gate(identity: EvidenceIdentity, gate: str, shards: tuple[str, ...]) -> EvidenceReceipt:
    return EvidenceReceipt(
        3,
        "reposeal.validation-evidence@3",
        "sha256:" + "9" * 64,
        identity,
        None,
        ValidationExecution((gate,), tuple(_outcome(name) for name in shards)),
        ValidationCompleteness(gate == "member", gate == "final", shards),
        ValidationProvenance(),
        {},
        True,
    )


@pytest.mark.parametrize(
    "different",
    [
        replace(_identity(), commit="f" * 40),
        replace(
            _identity(),
            configuration=ArtifactIdentity("reposeal.toml", "sha256:" + "1" * 64),
        ),
        replace(_identity(), tools=(ToolIdentity("uv", "0.8.15"),)),
    ],
)
def test_cross_identity_shards_cannot_be_combined(different: EvidenceIdentity) -> None:
    identity = _identity()

    with pytest.raises(ReceiptError, match="identity differs"):
        combine_shard_evidence(
            gate="final",
            required_shards=("core:static", "profile:python@test"),
            receipts=(
                _shard(identity, "core:static"),
                _shard(different, "profile:python@test"),
            ),
        )


def test_incomplete_shard_evidence_cannot_produce_gate_receipt() -> None:
    with pytest.raises(ReceiptError, match="missing shard evidence"):
        combine_shard_evidence(
            gate="final",
            required_shards=("core:static", "profile:python@test"),
            receipts=(_shard(_identity(), "core:static"),),
        )


def test_complete_shards_compose_one_exact_gate_receipt() -> None:
    identity = _identity()
    receipt = combine_shard_evidence(
        gate="final",
        required_shards=("core:static", "profile:python@test"),
        receipts=(
            _shard(identity, "profile:python@test"),
            _shard(identity, "core:static"),
        ),
    )

    assert receipt.schema_version == 3
    assert receipt.execution.gates == ("final",)
    assert receipt.execution.names == ("core:static", "profile:python@test")
    verify_gate_evidence(receipt, expected_identity=identity, gate="final")


def test_canonical_schema_digest_is_the_manifest_protocol_identity() -> None:
    assert evidence_schema_digest() == (
        "sha256:0c3d852d5f2a21856cfde4f31088f4a8527f98cf63d53614d073966187e5be12"
    )


def test_stale_gate_receipt_cannot_authorize_an_exact_tree() -> None:
    identity = _identity()
    receipt = combine_shard_evidence(
        gate="final",
        required_shards=("core:static",),
        receipts=(_shard(identity, "core:static"),),
    )

    with pytest.raises(ReceiptError, match="identity differs"):
        verify_gate_evidence(
            receipt,
            expected_identity=replace(identity, tree="f" * 40),
            gate="final",
        )


def test_receipt_json_round_trip_retains_the_complete_identity() -> None:
    receipt = _shard(_identity(), "core:static")

    assert EvidenceReceipt.from_json(receipt.to_json()) == receipt

    with pytest.raises(ReceiptError, match="invalid receipt document"):
        EvidenceReceipt.from_json("{}")


def test_combination_rejects_duplicate_unexpected_and_non_atomic_evidence() -> None:
    identity = _identity()
    shard = _shard(identity, "core:static")
    with pytest.raises(ReceiptError, match="duplicate shard evidence"):
        combine_shard_evidence(
            gate="final", required_shards=("core:static",), receipts=(shard, shard)
        )
    with pytest.raises(ReceiptError, match="unexpected shard evidence"):
        combine_shard_evidence(
            gate="final",
            required_shards=("core:static",),
            receipts=(
                _shard(identity, "core:static"),
                _shard(identity, "other:test"),
            ),
        )
    gate_receipt = _gate(identity, "member", ("core:static",))
    with pytest.raises(ReceiptError, match="only atomic shard evidence"):
        combine_shard_evidence(
            gate="final", required_shards=("core:static",), receipts=(gate_receipt,)
        )


@pytest.mark.parametrize(
    "operation",
    [
        lambda: ArtifactIdentity("/absolute", "sha256:" + "a" * 64),
        lambda: ArtifactIdentity("lock", "invalid"),
        lambda: ToolIdentity("", "version"),
        lambda: EvidenceIdentity(
            "bad",
            "b" * 40,
            None,
            ArtifactIdentity("config", "sha256:" + "a" * 64),
            (),
            "sha256:" + "b" * 64,
            (),
            (),
        ),
        lambda: replace(_gate(_identity(), "final", ("core:test",)), schema_version=2),
        lambda: replace(_gate(_identity(), "final", ("core:test",)), valid=False),
        lambda: replace(
            _gate(_identity(), "final", ("core:test",)),
            execution=ValidationExecution(("final", "final"), (_outcome("core:test"),)),
        ),
        lambda: replace(
            _gate(_identity(), "final", ("core:test",)),
            execution=ValidationExecution(
                ("final",), (_outcome("core:test"), _outcome("core:test"))
            ),
        ),
    ],
)
def test_receipt_values_fail_closed(operation: Callable[[], object]) -> None:
    with pytest.raises(ReceiptError):
        operation()


def _world(status: str, **overrides: object) -> ShardOutcome:
    values: dict[str, object] = {
        "name": "engine:audit",
        "command_digest": "sha256:" + "7" * 64,
        "evidence": "world",
        "status": status,
        "observed_at": "2026-09-02T00:00:00+00:00",
        "waivers": ("audit-example",),
        "findings": ("GHSA-aaaa-bbbb-cccc",),
    }
    values.update(overrides)
    return ShardOutcome(**values)  # type: ignore[arg-type]


def test_a_waived_world_outcome_names_its_authority_and_its_findings() -> None:
    outcome = _world("waived")

    assert outcome.waivers == ("audit-example",)
    assert outcome.findings == ("GHSA-aaaa-bbbb-cccc",)
    assert outcome.observed_at is not None


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda: _world("waived", evidence="tree"), id="tree-cannot-be-waived"),
        pytest.param(lambda: _world("waived", waivers=()), id="waived-needs-authority"),
        pytest.param(lambda: _world("waived", findings=()), id="waived-needs-findings"),
        pytest.param(lambda: _world("passed"), id="passed-carries-no-findings"),
        pytest.param(lambda: _world("waived", observed_at=None), id="world-records-observation"),
        pytest.param(
            lambda: ShardOutcome("t", "sha256:" + "8" * 64, "tree", "passed", "2026-09-02"),
            id="tree-observes-nothing",
        ),
        pytest.param(
            lambda: ShardOutcome("t", "sha256:" + "8" * 64, "quantum", "passed"),
            id="unsupported-evidence-class",
        ),
        pytest.param(
            lambda: ShardOutcome("t", "sha256:" + "8" * 64, "tree", "skipped"),
            id="unsupported-status",
        ),
        pytest.param(
            lambda: ShardOutcome("t", "not-a-digest", "tree", "passed"),
            id="command-digest-is-required",
        ),
    ],
)
def test_shard_outcomes_fail_closed(operation: Callable[[], object]) -> None:
    with pytest.raises(ReceiptError):
        operation()


def test_completeness_cannot_name_a_world_shard_which_never_ran() -> None:
    identity = _identity()
    with pytest.raises(ReceiptError, match="world shard which was not executed"):
        EvidenceReceipt(
            3,
            "reposeal.validation-evidence@3",
            "sha256:" + "9" * 64,
            identity,
            None,
            ValidationExecution(("final",), (_outcome("core:static"),)),
            ValidationCompleteness(False, True, ("core:static",), ("engine:audit",)),
            ValidationProvenance(),
            {},
            True,
        )
