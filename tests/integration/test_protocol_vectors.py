"""Signetum passes the conformance vectors it publishes for its consumers."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator

from signetum.resources import schemas as schema_resources
from signetum.resources import vectors as vector_resources
from signetum.resources.schemas import EVIDENCE_PROTOCOL, EVIDENCE_SCHEMA, evidence_schema_digest

VECTORS = "validation-evidence-v3.json"


def _published() -> dict[str, Any]:
    return json.loads((files(vector_resources) / VECTORS).read_text(encoding="utf-8"))


def _validator() -> Validator:
    document = json.loads((files(schema_resources) / EVIDENCE_SCHEMA).read_text(encoding="utf-8"))
    return Draft202012Validator(document)


def test_the_vectors_state_the_protocol_identity_a_consumer_pins() -> None:
    published = _published()

    assert published["protocol"] == EVIDENCE_PROTOCOL
    assert published["schema_digest"] == evidence_schema_digest()


def test_every_published_case_is_named_and_decided() -> None:
    cases = _published()["cases"]

    assert len(cases) >= 2
    assert {case["name"] for case in cases}.__len__() == len(cases)
    assert {case["valid"] for case in cases} == {True, False}
    for case in cases:
        assert case["valid"] or case["reason"]


@pytest.mark.parametrize("case", _published()["cases"], ids=lambda case: case["name"])
def test_this_runtime_agrees_with_its_own_published_vectors(case: dict[str, Any]) -> None:
    errors = sorted(_validator().iter_errors(case["document"]), key=str)

    if case["valid"]:
        assert errors == [], [f"{list(error.path)}: {error.message}" for error in errors]
    else:
        assert errors, f"expected a rejection: {case['reason']}"
