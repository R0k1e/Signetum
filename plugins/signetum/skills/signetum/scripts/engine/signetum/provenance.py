"""Committed batch provenance consumed by synchronization and delivery."""

import re
from pathlib import Path

from signetum.change.scope import delivered_plans, delivery_scope
from signetum.git import git_output, run_git
from signetum.manifest import load_manifest
from signetum.operations import AdmissionError


def attested_base(repository: Path, tip: str) -> str | None:
    """Read the base a batch's provenance commit attests to.

    This is the durable attestation, not the authority: operations read the
    workspace record. Delivery compares the two so a record which disagrees
    with committed history cannot land.
    """

    history = git_output(repository, "log", "--first-parent", "--format=%B%x00", tip)
    marker = re.search(r"^Signetum-Batch-Base:\s*(\S+)$", history, re.MULTILINE)
    return marker.group(1) if marker else None


def _synchronized_base(
    repository: Path, fields: dict[str, str], merged: str, in_effect: str | None
) -> str:
    """Advance the base in effect through one batch synchronization merge."""

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
        body = git_output(repository, "show", "-s", "--format=%B", merge_commit)
        fields = {
            key: value
            for key, value in re.findall(r"^Signetum-([^:]+):\s*(.+)$", body, re.MULTILINE)
        }
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
                # A stacked member names the member whose tip it was built on.
                **(
                    {"parent": fields["Parent"], "parent_tip": fields.get("Parent-Tip", "")}
                    if "Parent" in fields
                    else {}
                ),
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
