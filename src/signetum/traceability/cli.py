"""Versioned JSON public boundary for traceability checking and status queries."""

import argparse
import json
import sys
from enum import IntEnum
from pathlib import Path
from typing import TextIO

from signetum.change_record import load_repository_record
from signetum.serialization import contract_mapping
from signetum.source_authority import authority_roots
from signetum.status.models import EvidenceSnapshot
from signetum.status.projector import project_record_status
from signetum.traceability.boundary import (
    GitInventoryProvider,
    InventoryProvider,
    TraceabilityManifest,
)
from signetum.traceability.loading import load_decision
from signetum.traceability.records import record_issues
from signetum.traceability.validator import (
    decision_corpus_issues,
)


class ExitCode(IntEnum):
    SUCCESS = 0
    INVOCATION_ERROR = 2
    VALIDATION_FAILURE = 3
    INTERNAL_FAILURE = 4


def query(
    repository: Path,
    manifest: TraceabilityManifest,
    evidence: EvidenceSnapshot,
    stdout: TextIO,
    stderr: TextIO,
    inventory_provider: InventoryProvider | None = None,
) -> ExitCode:
    """Validate every declared change and emit exactly one JSON object."""
    try:
        provider = inventory_provider or GitInventoryProvider()
        inventory = provider.read(repository)
        changes_prefix = manifest.changes_root.rstrip("/") + "/"
        record_paths = sorted(
            path
            for path in inventory.paths
            if path.startswith(changes_prefix)
            and path.endswith("/change.toml")
            and len(Path(path).relative_to(manifest.changes_root).parts) == 2
        )
        records = tuple(
            (path, load_repository_record(repository, path, paths=inventory.paths))
            for path in record_paths
        )
        consolidated_issues = record_issues(records)
        # A decision root holds decisions: filtering by file name would make an
        # unrecognised name silently unchecked instead of refused.
        decision_paths = sorted(
            path
            for root in manifest.decision_roots
            for path in inventory.below(root)
            if path.endswith(".md")
        )
        decisions = tuple((path, load_decision(repository / path, path)) for path in decision_paths)
        corpus_issues = decision_corpus_issues(decisions)
        projections = (
            [project_record_status(path, record, evidence) for path, record in records]
            if not consolidated_issues
            else []
        )
        valid = bool(record_paths) and not corpus_issues and not consolidated_issues
        payload = {
            "schema_version": 1,
            "command": "traceability",
            "valid": valid,
            "changes": [contract_mapping(projection) for projection in projections],
            "issues": [
                contract_mapping(issue)
                for issue in (
                    *corpus_issues,
                    *consolidated_issues,
                )
            ],
        }
        stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        if not valid:
            for issue in payload["issues"][:20]:
                stderr.write(f"{issue['file']}:{issue['field']}: {issue['reason']}\n")
            return ExitCode.VALIDATION_FAILURE
        return ExitCode.SUCCESS
    except (OSError, KeyError, ValueError) as error:
        return _query_failure(error, stdout, stderr)


def _query_failure(error: Exception, stdout: TextIO, stderr: TextIO) -> ExitCode:
    stdout.write(
        json.dumps(
            {
                "schema_version": 1,
                "command": "traceability",
                "valid": False,
                "issues": [{"code": "invocation-error", "reason": str(error)}],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    stderr.write(f"traceability: {error}\n")
    return ExitCode.INVOCATION_ERROR


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--changes-root")
    parser.add_argument("--decision-root", action="append")
    parsed = parser.parse_args(arguments)
    try:
        default_root, default_decisions = authority_roots(parsed.repository)
        root = parsed.changes_root or default_root
        decisions = tuple(parsed.decision_root or (default_decisions,))
        authority = TraceabilityManifest(
            schema_version=1,
            changes_root=root,
            decision_roots=decisions,
        )
    except (OSError, ValueError) as error:
        return int(_query_failure(error, sys.stdout, sys.stderr))
    return int(query(parsed.repository, authority, EvidenceSnapshot(), sys.stdout, sys.stderr))


if __name__ == "__main__":
    raise SystemExit(main())
