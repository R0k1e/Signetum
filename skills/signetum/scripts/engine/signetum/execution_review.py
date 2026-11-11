"""Bind machine-local execution inputs to one immutable batch review."""

import hashlib
from dataclasses import asdict
from pathlib import Path

from signetum.change.revisions import authorization_history
from signetum.change.scope import batch_owned_commits, delivery_scope
from signetum.development_store import SourceReviewInputs
from signetum.development_store import review_inputs as source_review_inputs
from signetum.deviations import ReviewSnapshot, review_snapshot
from signetum.git import git_output, run_git
from signetum.manifest import RepositoryManifest
from signetum.operations import AdmissionError
from signetum.provenance import members_and_plans
from signetum.workspaces import WorkspaceError, branch_name, read_record, state_root


class ExecutionReviewInputs(ReviewSnapshot):
    member_evidence: dict[str, str]
    member_tips: dict[str, list[str]]
    member_chain: list[dict[str, object]]
    source_journals: SourceReviewInputs
    batch_commits: list[dict[str, object]]
    combination_repairs: list[dict[str, object]]
    authorization_history: dict[str, dict[str, object]]


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
    # Each admission is its own member and change; the member record names a parent.
    chain: list[dict[str, object]] = []
    for member in members:
        try:
            record = read_record(state_root(repository), member["branch"])
        except WorkspaceError:
            record = None
        parent = record.parent if record is not None else None
        chain.append(
            {
                "member": member["branch"],
                "original": member["original"],
                "changes": [Path(plan).parent.name for plan in member["plan"].split(",") if plan],
                "parent": parent,
                "parent_tip": record.base if record is not None and parent else None,
            }
        )
    batch_commits = batch_owned_commits(repository, manifest, base, tip)

    batch_record = read_record(state_root(repository), branch_name(repository))
    authorization = (
        {**asdict(batch_record.authorization), "members": list(batch_record.authorization.members)}
        if batch_record.authorization
        else None
    )
    repairs = [
        {
            "commit": item["commit"],
            "subject": git_output(repository, "show", "-s", "--format=%s", str(item["commit"])),
            "diffstat": git_output(repository, "show", "--format=", "--stat", str(item["commit"])),
            "authorization": authorization,
        }
        for item in batch_commits
        if item["authority"] == "batch-authorization"
    ]
    return {
        **snapshot,
        "member_evidence": fingerprints,
        "member_tips": tips,
        "member_chain": chain,
        "source_journals": source_journals,
        "batch_commits": batch_commits,
        "combination_repairs": repairs,
        "authorization_history": {
            change: authorization_history(
                repository, f"{manifest.repository.changes}/{change}/change.toml", tip
            )
            for change in source_changes
            if run_git(
                repository,
                "cat-file",
                "-e",
                f"{tip}:{manifest.repository.changes}/{change}/change.toml",
            ).returncode
            == 0
        },
    }
