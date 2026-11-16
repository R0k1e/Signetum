"""Remote-first publication of an already qualified exact batch identity."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from signetum.operation_records import (
    OperationIntent,
    commit_operation,
    complete_operation,
    freeze_message,
    intent_from_document,
    legacy_publication_commit,
    load_index,
    require_bound_commit,
)
from signetum.operations import AdmissionError, OperationFailed
from signetum.publication_push import guarded_push


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
    message: str,
) -> Publication:
    """Confirm remote publication before moving the local target, with exact retry.

    Callers own clean-workspace, policy, provenance and evidence qualification.
    They perform residue cleanup only after this publication returns.
    """
    message = freeze_message(message)
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
            raise AdmissionError(
                "remote delivery branch differs from expected base",
                expected=(
                    f"run maintenance workspace-sync in {source} to merge the delivery tip, "
                    "then final and batch-deliver at the new base"
                ),
            )
        resumed_commit = remote_before
    if target_head != expected_base and target_head != resumed_commit:
        raise AdmissionError("target tip differs from expected base or resumed delivery")
    if not is_ancestor(source, expected_base, expected_tip):
        raise AdmissionError("batch tip does not descend from expected base")
    tree = git(source, "rev-parse", f"{expected_tip}^{{tree}}")
    if resumed_commit is None:
        delivery_commit = commit_operation(
            source,
            _publication_intent(target_branch, expected_base, expected_tip, message, tree),
        )
        try:
            guarded_push(
                source,
                git=git,
                target_branch=target_branch,
                expected_base=expected_base,
                delivery_commit=delivery_commit,
            )
        except AdmissionError as error:
            raise OperationFailed(
                str(error), expected="inspect the remote base and retry batch-deliver"
            ) from error
    else:
        delivery_commit = _resume_publication(
            source,
            resumed_commit,
            _publication_intent(target_branch, expected_base, expected_tip, message, tree),
            target_branch,
        )
    remote_after = remote_tip(target, target_branch)
    if remote_after != delivery_commit:
        raise AdmissionError("remote delivery confirmation differs from delivered commit")
    git(target, "merge", "--ff-only", delivery_commit)
    return Publication(delivery_commit, remote_after)


def _resume_publication(
    repository: Path, commit: str, intent: OperationIntent, target_branch: str
) -> str:
    """Resume a publication that already has matching proof.

    An observed remote commit does not become a new operation. A retained old
    publication stays on its explicit legacy evidence and is not recorded again.
    """

    matches = [
        document
        for document in load_index(repository).by_id.values()
        if document.get("kind") == intent.kind
        and document.get("branch") == intent.branch
        and document.get("before") == intent.before
        and document.get("source") == intent.source
        and document.get("base") == intent.base
        and document.get("attested_base") == intent.attested_base
        and document.get("parents") == list(intent.parents)
        and document.get("tree") == intent.tree
        and document.get("message") == intent.message
    ]
    if len(matches) > 1:
        raise AdmissionError("conflicting operation proofs claim one commit")
    if len(matches) == 1:
        document = matches[0]
        stored = intent_from_document(document)
        if document.get("status") != "completed":
            document = complete_operation(repository, stored, commit)
        proof = require_bound_commit(repository, document)
        if proof.get("commit") != commit:
            raise AdmissionError("completed operation proof conflicts with the remote commit")
        return commit
    if legacy_publication_commit(repository, commit, target_branch, intent.base, intent.source):
        return commit
    raise AdmissionError(
        "remote publication has no matching operation proof",
        expected="retry the publication that recorded this commit, or adopt its legacy history",
    )


def _publication_intent(
    branch: str, expected_base: str, expected_tip: str, message: str, tree: str
) -> OperationIntent:
    return OperationIntent(
        kind="publication",
        branch=branch,
        before=expected_base,
        source=expected_tip,
        base=expected_base,
        message=message,
        attested_base=expected_base,
        parents=(expected_base, expected_tip),
        tree=tree,
    )
