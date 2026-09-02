"""Emit the Signetum findings document for the current pip-audit report.

A world validation shard reports through this document, never through a tool's
native output, so the lifecycle can match findings against tracked waivers
without knowing anything about the tool that produced them.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 -- fixed argv, never a shell
import sys
from shutil import which
from typing import Any

FINDINGS_SCHEMA_VERSION = 1
PIP_AUDIT_COMMAND = ("pip-audit", "--format", "json")


class FindingsError(ValueError):
    """pip-audit did not produce a translatable report."""


def _dependencies(document: str) -> list[dict[str, Any]]:
    try:
        raw = json.loads(document)
    except json.JSONDecodeError as error:
        raise FindingsError(f"pip-audit did not emit JSON: {error.msg}") from error
    entries = raw.get("dependencies") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise FindingsError("pip-audit JSON has no dependency array")
    return [entry for entry in entries if isinstance(entry, dict)]


def translate(document: str) -> str:
    """Return the Signetum findings document for one pip-audit JSON report."""

    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for dependency in _dependencies(document):
        name = str(dependency.get("name", "")).strip()
        version = str(dependency.get("version", "")).strip()
        vulnerabilities = dependency.get("vulns")
        if not name or not isinstance(vulnerabilities, list):
            continue
        locator = f"pip:{name}@{version}" if version else f"pip:{name}"
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                continue
            identifier = str(vulnerability.get("id", "")).strip()
            if not identifier or (identifier, locator) in seen:
                continue
            seen.add((identifier, locator))
            description = str(vulnerability.get("description", "") or "").strip()
            summary = description.splitlines()[0] if description else ""
            findings.append(
                {
                    "id": identifier,
                    "locator": locator,
                    "summary": summary or f"{name} {version} is affected by {identifier}",
                }
            )
    findings.sort(key=lambda item: (item["id"], item["locator"]))
    return json.dumps(
        {"schema_version": FINDINGS_SCHEMA_VERSION, "findings": findings},
        sort_keys=True,
        separators=(",", ":"),
    )


def main() -> int:
    """Run pip-audit and print exactly one findings document."""

    executable = which(PIP_AUDIT_COMMAND[0])
    if executable is None:
        print("pip-audit executable is unavailable", file=sys.stderr)
        return 2
    completed = subprocess.run(  # nosec B603
        (executable, *PIP_AUDIT_COMMAND[1:]),
        check=False,
        capture_output=True,
        text=True,
    )
    if not completed.stdout.strip():
        print(completed.stderr.strip() or "pip-audit produced no report", file=sys.stderr)
        return 2
    try:
        print(translate(completed.stdout))
    except FindingsError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
