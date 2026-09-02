"""Versioned JSON public boundary for traceability checking and status queries."""

import json
from enum import IntEnum
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from signetum.status.models import EvidenceSnapshot
from signetum.status.projector import project_status
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
        valid = bool(review_paths) and all(report.valid for report in reports) and not corpus_issues
        payload = {
            "schema_version": 1,
            "command": "traceability",
            "valid": valid,
            "changes": [projection.model_dump(mode="json") for projection in projections],
            "issues": [
                issue.model_dump(mode="json")
                for issue in (
                    *(issue for report in reports for issue in report.issues),
                    *corpus_issues,
                )
            ],
        }
        stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        if not valid:
            for issue in payload["issues"][:20]:
                stderr.write(f"{issue['file']}:{issue['field']}: {issue['reason']}\n")
            return ExitCode.VALIDATION_FAILURE
        return ExitCode.SUCCESS
    except (OSError, KeyError, ValueError, ValidationError) as error:
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
