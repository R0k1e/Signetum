# Generated from signetum.execution_review; edit the engine source and regenerate.
"""Bind machine-local execution inputs to one immutable batch review."""

import hashlib
from pathlib import Path

from .change_scope import delivery_scope
from .development_store import SourceReviewInputs
from .development_store import review_inputs as source_review_inputs
from .deviations import ReviewSnapshot, review_snapshot
from .git import git_output
from .manifest import RepositoryManifest
from .operations import AdmissionError
from .provenance import members_and_plans


class ExecutionReviewInputs(ReviewSnapshot):
    member_evidence: dict[str, str]
    member_tips: dict[str, list[str]]
    source_journals: SourceReviewInputs


def execution_review_inputs(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str, receipt_root: Path
) -> ExecutionReviewInputs:
    scope = delivery_scope(repository, manifest, base, tip)
    members = []
    if git_output(repository, "rev-list", "--first-parent", "--merges", f"{base}..{tip}"):
        members, _ = members_and_plans(repository, base, tip)
    fingerprints: dict[str, str] = {}
    for member in members:
        name = member["ready_evidence"]
        if not name or Path(name).name != name:
            raise AdmissionError("admitted member evidence has an invalid receipt path")
        try:
            fingerprints[name] = hashlib.sha256((receipt_root / name).read_bytes()).hexdigest()
        except OSError as error:
            raise AdmissionError(
                f"admitted member evidence is unavailable: {name}: {error}"
            ) from error
    tips = {
        member["branch"]: [
            item["original"] for item in members if item["branch"] == member["branch"]
        ]
        for member in members
    }
    snapshot = review_snapshot(
        repository,
        scope.first_delivered,
        tuple(item["branch"] for item in members),
        member_tips=tips,
    )
    source_changes = tuple(
        sorted(
            set(
                (
                    *snapshot["changes"],
                    *(item.change_id for item in scope.previously_delivered),
                )
            )
        )
    )
    source_journals = source_review_inputs(repository, source_changes, commit=tip)
    return {
        **snapshot,
        "member_evidence": fingerprints,
        "member_tips": tips,
        "source_journals": source_journals,
    }
