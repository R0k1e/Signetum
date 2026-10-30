"""Remote-first publication of an already qualified exact batch identity."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from signetum.operations import AdmissionError, OperationFailed


class GitCommand(Protocol):
    def __call__(self, repository: Path, *arguments: str) -> str: ...


@dataclass(frozen=True)
class Publication:
    commit: str
    remote: str


def publish_batch(
    source: Path,
    target: Path,
    expected_base: str,
    expected_tip: str,
    target_branch: str,
    *,
    git: GitCommand,
    remote_tip: Callable[[Path, str], str],
    is_ancestor: Callable[[Path, str, str], bool],
) -> Publication:
    """Confirm remote publication before moving the local target, with exact retry.

    Callers own clean-workspace, policy, provenance and evidence qualification.
    They perform residue cleanup only after this publication returns.
    """
    if git(source, "rev-parse", "HEAD") != expected_tip:
        raise AdmissionError("source tip differs from expected batch tip")
    target_head = git(target, "rev-parse", "HEAD")
    remote_before = remote_tip(target, target_branch)
    resumed_commit = None
    if remote_before != expected_base:
        git(source, "fetch", "--no-tags", "origin", f"refs/heads/{target_branch}")
        parents = git(source, "show", "-s", "--format=%P", remote_before).split()
        remote_tree = git(source, "rev-parse", f"{remote_before}^{{tree}}")
        source_tree = git(source, "rev-parse", f"{expected_tip}^{{tree}}")
        if parents != [expected_base, expected_tip] or remote_tree != source_tree:
            raise AdmissionError("remote delivery branch differs from expected base")
        resumed_commit = remote_before
    if target_head != expected_base and target_head != resumed_commit:
        raise AdmissionError("target tip differs from expected base or resumed delivery")
    if not is_ancestor(source, expected_base, expected_tip):
        raise AdmissionError("batch tip does not descend from expected base")
    if resumed_commit is None:
        delivery_commit = git(
            source,
            "commit-tree",
            f"{expected_tip}^{{tree}}",
            "-p",
            expected_base,
            "-p",
            expected_tip,
            "-m",
            f"Merge validated batch {expected_tip}\n\nSignetum-Batch-Base: {expected_base}",
        )
        try:
            git(source, "push", "origin", f"{delivery_commit}:refs/heads/{target_branch}")
        except AdmissionError as error:
            raise OperationFailed(
                str(error), expected="inspect the remote base and retry batch-deliver"
            ) from error
    else:
        delivery_commit = resumed_commit
    remote_after = remote_tip(target, target_branch)
    if remote_after != delivery_commit:
        raise AdmissionError("remote delivery confirmation differs from delivered commit")
    git(target, "merge", "--ff-only", delivery_commit)
    return Publication(delivery_commit, remote_after)
