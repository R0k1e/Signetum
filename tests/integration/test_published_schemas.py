"""The published schemas are enforced against what this repository ships."""

from __future__ import annotations

import json
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator

from signetum.evidence.receipts import (
    ArtifactIdentity,
    EvidenceIdentity,
    EvidenceReceipt,
    ShardOutcome,
    ValidationCompleteness,
    ValidationExecution,
    ValidationProvenance,
)
from signetum.manifest import load_manifest
from signetum.resources import schemas as schema_resources
from signetum.resources.schemas import EVIDENCE_PROTOCOL, evidence_schema_digest

REPOSITORY = Path(__file__).resolve().parents[2]
MANIFESTS = ("signetum.toml", "template/signetum.toml")


def _schema(name: str) -> Validator:
    document = json.loads((files(schema_resources) / name).read_text(encoding="utf-8"))
    return Draft202012Validator(document)


def _violations(schema: str, document: object) -> list[str]:
    """Return one readable line per schema violation, most specific first."""

    errors = sorted(_schema(schema).iter_errors(document), key=str)
    return [f"{list(error.path)}: {error.message}" for error in errors]


@pytest.mark.parametrize("relative", MANIFESTS)
def test_shipped_manifests_satisfy_the_published_manifest_schema(relative: str) -> None:
    document = tomllib.loads((REPOSITORY / relative).read_text(encoding="utf-8"))

    assert _violations("signetum-v2.schema.json", document) == []


@pytest.mark.parametrize("relative", MANIFESTS)
def test_shipped_manifests_identify_the_shipped_evidence_schema(relative: str) -> None:
    manifest = load_manifest(REPOSITORY / relative)
    assert manifest.signetum.evidence_protocol == EVIDENCE_PROTOCOL
    assert manifest.signetum.evidence_schema_digest == evidence_schema_digest()


def _receipt(
    execution: ValidationExecution, completeness: ValidationCompleteness
) -> dict[str, Any]:
    identity = EvidenceIdentity(
        commit="a" * 40,
        tree="b" * 40,
        base="c" * 40,
        configuration=ArtifactIdentity("signetum.toml", "sha256:" + "1" * 64),
        profiles=("python-default@1",),
        graph="sha256:" + "2" * 64,
        lockfiles=(ArtifactIdentity("uv.lock", "sha256:" + "3" * 64),),
        tools=(),
    )
    receipt = EvidenceReceipt(
        3,
        EVIDENCE_PROTOCOL,
        evidence_schema_digest(),
        identity,
        None,
        execution,
        completeness,
        ValidationProvenance(),
        {},
        True,
    )
    return json.loads(receipt.to_json())


def test_a_passed_gate_receipt_satisfies_the_published_evidence_schema() -> None:
    outcome = ShardOutcome("engine:ruff", "sha256:" + "4" * 64, "tree", "passed")
    document = _receipt(
        ValidationExecution(("member",), (outcome,)),
        ValidationCompleteness(True, False, ("engine:ruff",)),
    )
    assert _violations("validation-evidence-v3.schema.json", document) == []


def test_a_waived_world_shard_receipt_satisfies_the_published_evidence_schema() -> None:
    outcome = ShardOutcome(
        "engine:audit",
        "sha256:" + "5" * 64,
        "world",
        "waived",
        "2026-09-02T00:00:00+00:00",
        ("audit-ghsa-example",),
        ("GHSA-aaaa-bbbb-cccc",),
    )
    document = _receipt(
        ValidationExecution(("final",), (outcome,)),
        ValidationCompleteness(False, True, ("engine:audit",), ("engine:audit",)),
    )
    assert _violations("validation-evidence-v3.schema.json", document) == []
