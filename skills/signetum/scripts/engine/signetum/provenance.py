"""Committed batch provenance consumed by synchronization and delivery."""

import re
from pathlib import Path

from signetum.change.scope import delivered_plans, delivery_scope
from signetum.git import git_output, run_git
from signetum.manifest import load_manifest
from signetum.operation_records import (
    attested_base_from,
    batch_sync_record,
    bind_commit_if_pending,
    legacy_commit,
    legacy_pending_commit,
    legacy_proof_message,
    load_index,
    member_from_record,
    require_bound_commit,
    require_qualification,
)
from signetum.operations import AdmissionError


def attested_base(repository: Path, tip: str) -> str | None:
    """Read the base a batch's provenance commit attests to.

    Structured operations are the authority for new history. A legacy commit
    remains readable. Delivery still compares the result with the workspace
    record so a disagreement cannot land.
    """

    return attested_base_from(repository, tip)


def _legacy_fields(body: str) -> dict[str, str]:
    return {
        key: value for key, value in re.findall(r"^Signetum-([^:]+):\s*(.+)$", body, re.MULTILINE)
    }


def _synchronized_base(
    repository: Path, fields: dict[str, str], merged: str, in_effect: str | None
) -> str:
    """Advance the base in effect through one legacy batch synchronization merge."""

    previous = fields.get("Previous-Batch-Base")
    if (
        "Member" in fields
        or fields.get("Batch-Sync") != merged
        or fields.get("Batch-Base") != merged
        or not previous
        or (in_effect is not None and previous != in_effect)
    ):
        raise AdmissionError("batch contains an unrecognized synchronization merge")
    if run_git(repository, "merge-base", "--is-ancestor", previous, merged).returncode:
        raise AdmissionError("batch synchronization does not descend from the previous base")
    return merged


def _legacy_visible(repository: Path, commit: str) -> bool:
    return legacy_commit(repository, commit) or legacy_pending_commit(repository, commit)


def latest_admission_original(repository: Path, base: str, tip: str, member: str) -> str | None:
    """The latest admitted original of ``member`` in this batch history."""

    try:
        members, _ = members_and_plans(repository, base, tip)
    except AdmissionError:
        return None
    originals = [item["original"] for item in members if item["branch"] == member]
    return originals[-1] if originals else None


def members_and_plans(
    repository: Path, expected_base: str, expected_tip: str
) -> tuple[list[dict[str, str]], list[str]]:
    merge_commits = tuple(
        filter(
            None,
            git_output(
                repository,
                "rev-list",
                "--reverse",
                "--first-parent",
                "--merges",
                f"{expected_base}..{expected_tip}",
            ).splitlines(),
        )
    )
    index = load_index(repository)
    members: list[dict[str, str]] = []
    # Admissions bind the base in effect when they merged; a synchronization
    # merge advances it to the delivery tip it merged. The chain ends at the
    # expected base.
    in_effect: str | None = None
    synchronized = False
    for merge_commit in merge_commits:
        parents = git_output(repository, "show", "-s", "--format=%P", merge_commit).split()
        if len(parents) != 2:
            raise AdmissionError("batch contains a merge without exactly one admitted member")
        original = parents[1]
        document = index.for_commit(merge_commit)
        if document is None:
            document = bind_commit_if_pending(repository, merge_commit)
        if document is not None:
            require_bound_commit(repository, document)
            synced = batch_sync_record(document)
            if synced is not None:
                previous, merged = synced
                if merged != original or (in_effect is not None and previous != in_effect):
                    raise AdmissionError("batch contains an unrecognized synchronization merge")
                if run_git(repository, "merge-base", "--is-ancestor", previous, merged).returncode:
                    raise AdmissionError(
                        "batch synchronization does not descend from the previous base"
                    )
                in_effect = merged
                synchronized = True
                continue
            if document.get("kind") != "admission":
                raise AdmissionError("batch contains an unrecognized merge authority")
            if document.get("source") != original or document.get("attested_base") != (
                in_effect if in_effect is not None else document.get("attested_base")
            ):
                raise AdmissionError("admission provenance original does not match merge parent")
            if in_effect is None:
                attested = document.get("attested_base")
                if not isinstance(attested, str):
                    raise AdmissionError("admission record has no base")
                in_effect = attested
            if document.get("attested_base") != in_effect:
                raise AdmissionError("batch contains an unrecognized merge authority")
            digest = document.get("ready_evidence_sha256")
            if isinstance(digest, str) and digest:
                require_qualification(repository, digest)
            summary = git_output(repository, "show", "-s", "--format=%s", original)
            members.append(member_from_record(document, merge_commit, summary))
            continue
        if not _legacy_visible(repository, merge_commit):
            raise AdmissionError("batch contains an unrecorded merge")
        body = git_output(repository, "show", "-s", "--format=%B", merge_commit)
        if not legacy_proof_message(body):
            raise AdmissionError("batch contains an unrecognized merge authority")
        fields = _legacy_fields(body)
        if "Batch-Sync" in fields:
            in_effect = _synchronized_base(repository, fields, original, in_effect)
            synchronized = True
            continue
        if in_effect is None:
            in_effect = fields.get("Batch-Base")
        if not fields.get("Member") or fields.get("Batch-Base") != in_effect:
            raise AdmissionError("batch contains an unrecognized merge authority")
        if fields.get("Original") != original:
            raise AdmissionError("admission provenance original does not match merge parent")
        summary = git_output(repository, "show", "-s", "--format=%s", original)
        member_plans = re.findall(r"^Signetum-Plan:\s*(.+)$", body, re.MULTILINE)
        members.append(
            {
                "branch": fields["Member"],
                "original": original,
                "patch_id": fields.get("Patch-ID", ""),
                "ready_evidence": fields.get("Ready-Evidence", ""),
                "plan": ",".join(member_plans),
                "admission_commit": merge_commit,
                "summary": summary,
            }
        )
    if in_effect is not None and in_effect != expected_base:
        if not synchronized:
            raise AdmissionError("batch contains an unrecognized merge authority")
        raise AdmissionError(
            f"batch history is synchronized to base {in_effect}, not {expected_base}"
        )
    if not members:
        raise AdmissionError("batch contains no admitted member provenance")
    manifest = load_manifest(repository / "signetum.toml")
    scope = delivery_scope(repository, manifest, expected_base, expected_tip)
    return members, list(delivered_plans(repository, manifest, scope.first_delivered, expected_tip))
