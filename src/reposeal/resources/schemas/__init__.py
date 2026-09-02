"""Versioned JSON schemas."""

from hashlib import sha256
from importlib.resources import files

EVIDENCE_PROTOCOL = "reposeal.validation-evidence@3"
EVIDENCE_SCHEMA = "validation-evidence-v3.schema.json"


def evidence_schema_digest() -> str:
    content = (files(__package__) / EVIDENCE_SCHEMA).read_bytes()
    return "sha256:" + sha256(content).hexdigest()


__all__ = ["EVIDENCE_PROTOCOL", "EVIDENCE_SCHEMA", "evidence_schema_digest"]
