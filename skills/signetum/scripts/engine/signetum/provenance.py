"""Committed batch provenance consumed by synchronization and delivery."""

from pathlib import Path

from signetum.change.scope import delivered_plans, delivery_scope
from signetum.git import git_output, run_git
from signetum.manifest import load_manifest
from signetum.operation_records import (
    attested_base_from,
    batch_sync_record,
    bind_commit_if_pending,
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
                in_effect = str(document["attested_base"])
            digest = document.get("ready_evidence_sha256")
            if isinstance(digest, str) and digest:
                require_qualification(repository, digest)
            summary = git_output(repository, "show", "-s", "--format=%s", original)
            members.append(member_from_record(document, merge_commit, summary))
            continue
        raise AdmissionError(
            "batch contains an unrecorded merge",
            expected="finish a batch an older engine opened with that engine",
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
