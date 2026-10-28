# Generated from signetum.provenance; edit the engine source and regenerate.
"""Committed batch provenance consumed by synchronization and delivery."""

import re
from pathlib import Path

from .change_scope import delivered_plans, delivery_scope
from .git import git_output
from .manifest import load_manifest
from .operations import AdmissionError


def attested_base(repository: Path, tip: str) -> str | None:
    """Read the base a batch's provenance commit attests to.

    This is the durable attestation, not the authority: operations read the
    workspace record. Delivery compares the two so a record which disagrees
    with committed history cannot land.
    """

    history = git_output(repository, "log", "--first-parent", "--format=%B%x00", tip)
    marker = re.search(r"^Signetum-Batch-Base:\s*(\S+)$", history, re.MULTILINE)
    return marker.group(1) if marker else None


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
    for merge_commit in merge_commits:
        parents = git_output(repository, "show", "-s", "--format=%P", merge_commit).split()
        if len(parents) != 2:
            raise AdmissionError("batch contains a merge without exactly one admitted member")
        subject = git_output(repository, "show", "-s", "--format=%s", merge_commit)
        prefix = "merge: admit "
        if not subject.startswith(prefix):
            raise AdmissionError("batch contains an unrecognized merge authority")
        original = parents[1]
        body = git_output(repository, "show", "-s", "--format=%B", merge_commit)
        fields = {
            key: value
            for key, value in re.findall(r"^Signetum-([^:]+):\s*(.+)$", body, re.MULTILINE)
        }
        if fields.get("Original") != original:
            raise AdmissionError("admission provenance original does not match merge parent")
        summary = git_output(repository, "show", "-s", "--format=%s", original)
        member_plans = re.findall(r"^Signetum-Plan:\s*(.+)$", body, re.MULTILINE)
        members.append(
            {
                "branch": subject.removeprefix(prefix),
                "original": original,
                "patch_id": fields.get("Patch-ID", ""),
                "ready_evidence": fields.get("Ready-Evidence", ""),
                "plan": ",".join(member_plans),
                "admission_commit": merge_commit,
                "summary": summary,
            }
        )
    if not members:
        raise AdmissionError("batch contains no admitted member provenance")
    manifest = load_manifest(repository / "signetum.toml")
    scope = delivery_scope(repository, manifest, expected_base, expected_tip)
    return members, list(delivered_plans(repository, manifest, scope.first_delivered, expected_tip))
