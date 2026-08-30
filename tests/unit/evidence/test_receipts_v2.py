from collections.abc import Callable
from dataclasses import replace

import pytest

from reposeal.evidence.receipts import (
    ArtifactIdentity,
    EvidenceIdentity,
    EvidenceReceipt,
    ReceiptError,
    ToolIdentity,
    combine_shard_evidence,
    verify_gate_evidence,
)


def _identity() -> EvidenceIdentity:
    return EvidenceIdentity(
        commit="a" * 40,
        tree="b" * 40,
        configuration=ArtifactIdentity("reposeal.toml", "sha256:" + "c" * 64),
        profiles=("python-default@2",),
        graph="sha256:" + "d" * 64,
        lockfiles=(ArtifactIdentity("uv.lock", "sha256:" + "e" * 64),),
        tools=(ToolIdentity("ruff", "0.12.9"), ToolIdentity("uv", "0.8.14")),
    )


def _shard(identity: EvidenceIdentity, name: str) -> EvidenceReceipt:
    return EvidenceReceipt.shard(identity=identity, shard=name)


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

    assert receipt.schema_version == 2
    assert receipt.executed_gates == ("final",)
    assert receipt.executed_shards == ("core:static", "profile:python@test")
    verify_gate_evidence(receipt, expected_identity=identity, gate="final")


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
    receipt = EvidenceReceipt.shard(identity=_identity(), shard="core:static")

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
    gate_receipt = EvidenceReceipt(2, identity, ("member",), ("core:static",), True)
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
            ArtifactIdentity("config", "sha256:" + "a" * 64),
            (),
            "sha256:" + "b" * 64,
            (),
            (),
        ),
        lambda: EvidenceReceipt(1, _identity(), (), ("core:test",), True),
        lambda: EvidenceReceipt(2, _identity(), (), ("core:test",), False),
        lambda: EvidenceReceipt(2, _identity(), ("final", "final"), ("core:test",), True),
        lambda: EvidenceReceipt(2, _identity(), (), ("core:test", "core:test"), True),
    ],
)
def test_receipt_values_fail_closed(operation: Callable[[], object]) -> None:
    with pytest.raises(ReceiptError):
        operation()
