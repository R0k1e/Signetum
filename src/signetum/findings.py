"""Tool-neutral findings document reported by a world validation shard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from re import fullmatch

FINDINGS_SCHEMA_VERSION = 1

_IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9._:@/-]*"


class FindingsError(ValueError):
    """A findings command did not emit one valid Signetum findings document."""


@dataclass(frozen=True, order=True)
class Finding:
    """One externally reported obligation a world shard observed."""

    id: str
    locator: str
    summary: str

    def __post_init__(self) -> None:
        if fullmatch(_IDENTIFIER, self.id) is None:
            raise FindingsError(f"finding id must be an identifier: {self.id}")
        if not self.locator:
            raise FindingsError(f"finding locator must be non-empty: {self.id}")
        if not self.summary:
            raise FindingsError(f"finding summary must be non-empty: {self.id}")


def parse_findings(document: str) -> tuple[Finding, ...]:
    """Read the exact findings document a world shard is required to emit.

    Signetum never parses a tool's native output. A profile or adapter owns that
    translation and emits this document instead.
    """

    try:
        raw = json.loads(document)
    except json.JSONDecodeError as error:
        raise FindingsError(f"findings document is not JSON: {error.msg}") from error
    if not isinstance(raw, dict):
        raise FindingsError("findings document must be an object")
    if raw.get("schema_version") != FINDINGS_SCHEMA_VERSION:
        raise FindingsError(f"unsupported findings schema: {raw.get('schema_version')}")
    entries = raw.get("findings")
    if not isinstance(entries, list):
        raise FindingsError("findings must be an array")
    findings: list[Finding] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise FindingsError("each finding must be an object")
        missing = {"id", "locator", "summary"} - set(entry)
        if missing:
            raise FindingsError(f"finding is missing {', '.join(sorted(missing))}")
        if set(entry) - {"id", "locator", "summary"}:
            raise FindingsError("finding carries unsupported fields")
        if not all(isinstance(entry[field], str) for field in ("id", "locator", "summary")):
            raise FindingsError("finding fields must be strings")
        finding = Finding(entry["id"], entry["locator"], entry["summary"])
        key = f"{finding.id}\x00{finding.locator}"
        if key in seen:
            raise FindingsError(f"duplicate finding: {finding.id} at {finding.locator}")
        seen.add(key)
        findings.append(finding)
    return tuple(sorted(findings))


__all__ = ["FINDINGS_SCHEMA_VERSION", "Finding", "FindingsError", "parse_findings"]
