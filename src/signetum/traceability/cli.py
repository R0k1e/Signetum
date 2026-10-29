"""Versioned JSON public boundary for traceability checking and status queries."""

import argparse
import json
import sys
from enum import IntEnum
from pathlib import Path
from typing import TextIO

from signetum.change.paths import changes_root
from signetum.change_record import load_repository_record
from signetum.manifest import load_manifest
from signetum.serialization import contract_mapping
from signetum.status.models import EvidenceSnapshot
from signetum.status.projector import project_record_status, project_status
from signetum.traceability.boundary import (
    GitInventoryProvider,
    InventoryProvider,
    TraceabilityManifest,
)
from signetum.traceability.loading import (
    load_decision,
    load_plan,
    load_review,
    load_specification,
)
from signetum.traceability.records import record_issues
from signetum.traceability.validator import (
    TraceabilityValidator,
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
        review_paths = sorted(
            path
            for path in inventory.paths
            if path.startswith(changes_prefix) and path.endswith("/review.toml")
        )
        reviews = {path: load_review(repository / path) for path in review_paths}
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
        review_ids = frozenset(review.id for review in reviews.values())
        reports = []
        projections = []
        for review_path in review_paths:
            change_root = review_path.removesuffix("/review.toml")
            change_id = Path(change_root).name
            specification_paths = sorted(
                path
                for path in inventory.paths
                if path.startswith(f"{change_root}/specs/") and path.endswith(".toml")
            )
            review = reviews[review_path]
            specifications = tuple(
                (path, load_specification(repository / path)) for path in specification_paths
            )
            plan_paths = sorted({specification.plan for _, specification in specifications})
            plans = tuple(
                (path, load_plan(repository / path, change_id))
                for path in plan_paths
                if inventory.contains(path)
            )
            report = TraceabilityValidator().validate(
                manifest,
                inventory,
                review_path,
                review,
                specifications,
                plans,
                review_ids,
                decisions,
            )
            reports.append(report)
            if report.valid:
                projections.append(
                    project_status(
                        review,
                        tuple(item for _, item in specifications),
                        tuple(item for _, item in plans),
                        evidence,
                    )
                )
        if not consolidated_issues:
            projections.extend(
                project_record_status(path, record, evidence) for path, record in records
            )
        valid = (
            bool(review_paths or record_paths)
            and all(report.valid for report in reports)
            and not corpus_issues
            and not consolidated_issues
        )
        payload = {
            "schema_version": 1,
            "command": "traceability",
            "valid": valid,
            "changes": [contract_mapping(projection) for projection in projections],
            "issues": [
                contract_mapping(issue)
                for issue in (
                    *(issue for report in reports for issue in report.issues),
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
    parser.add_argument("--legacy-root", action="append", default=[])
    parsed = parser.parse_args(arguments)
    try:
        if parsed.changes_root is None or parsed.decision_root is None:
            manifest = load_manifest(parsed.repository / "signetum.toml")
            root = parsed.changes_root or changes_root(manifest)
            decisions = tuple(parsed.decision_root or (manifest.repository.decisions,))
        else:
            root, decisions = parsed.changes_root, tuple(parsed.decision_root)
        authority = TraceabilityManifest(
            schema_version=1,
            changes_root=root,
            decision_roots=decisions,
            legacy_roots=tuple(parsed.legacy_root),
        )
    except (OSError, ValueError) as error:
        return int(_query_failure(error, sys.stdout, sys.stderr))
    return int(query(parsed.repository, authority, EvidenceSnapshot(), sys.stdout, sys.stderr))


if __name__ == "__main__":
    raise SystemExit(main())
