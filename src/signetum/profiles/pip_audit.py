"""Translate pip-audit output into the tool-neutral Signetum findings document."""

from __future__ import annotations

import json
import subprocess  # nosec B404 -- fixed argv, never a shell
from shutil import which
from typing import Any

from signetum.findings import FINDINGS_SCHEMA_VERSION, FindingsError

PIP_AUDIT_COMMAND = ("pip-audit", "--format", "json")


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


def report() -> str:
    """Run pip-audit and translate whatever it reports.

    pip-audit exits nonzero precisely when it finds something, so the exit
    status is not an error condition here; the document is the result.
    """

    executable = which(PIP_AUDIT_COMMAND[0])
    if executable is None:
        raise FindingsError("pip-audit executable is unavailable")
    completed = subprocess.run(  # nosec B603
        (executable, *PIP_AUDIT_COMMAND[1:]),
        check=False,
        capture_output=True,
        text=True,
    )
    if not completed.stdout.strip():
        diagnostic = completed.stderr.strip() or "pip-audit produced no report"
        raise FindingsError(diagnostic)
    return translate(completed.stdout)


__all__ = ["PIP_AUDIT_COMMAND", "report", "translate"]
