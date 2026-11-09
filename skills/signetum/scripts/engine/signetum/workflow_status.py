"""Read workflow authorities without checks, network access or another status store.

Open workspaces are listed with the outcome each proves against the last fetched
delivery branch; cleanup proves it again against a fresh fetch before removal.
"""

import json
from pathlib import Path

from signetum.change.scope import (
    APPROVAL_ORDER_REMEDY,
    ChangeError,
    approval_order,
    records_only_ancestors,
)
from signetum.change_record import parse_change_record
from signetum.development_log import DevelopmentSnapshot
from signetum.evidence.receipts import ArtifactIdentity, EvidenceReceipt, ReceiptError
from signetum.gate_records import failed_tip, pending_admissions
from signetum.git import git_output, repository_path
from signetum.manifest import ManifestError, load_manifest
from signetum.serialization import contract_mapping
from signetum.source_authority import authority_roots, source_path
from signetum.stacking import admission_order, parent_moved
from signetum.workspace_operations import workspace_endings
from signetum.workspaces import current_branch, read_change_owner, read_record, record_path


def _manifest_cause(repository: Path) -> str | None:
    """Why this engine cannot load the manifest; status reads only its locations."""
    path = repository / "signetum.toml"
    if not path.exists():
        return None
    try:
        load_manifest(path)
    except ManifestError as error:
        return str(error)
    return None


def workflow_status(
    repository: Path, snapshot: DevelopmentSnapshot, *, source: str, verbose: bool = False
) -> dict[str, object]:
    repository = repository.resolve()
    if git_output(repository, "rev-parse", "HEAD") != source:
        raise ValueError("source changed while reading status")
    branch = current_branch(repository)
    common = repository_path(repository, "rev-parse", "--git-common-dir")
    root = common / "signetum"
    registered = record_path(root, branch).exists() if branch else False
    workspace = read_record(root, branch) if registered else None
    dirty = bool(git_output(repository, "status", "--porcelain"))
    merging = repository_path(repository, "rev-parse", "--git-path", "MERGE_HEAD").exists()
    change_root, _ = authority_roots(repository)
    manifest_cause = _manifest_cause(repository)
    changes = []
    for path in sorted((repository / change_root).glob("*/change.toml")):
        record = parse_change_record(
            source_path(repository, path.relative_to(repository).as_posix()).read_text()
        )
        owner = read_change_owner(root, record.id)
        member_match = (
            workspace is not None
            and workspace.kind == "member"
            and record.contract.approved_base == workspace.base
            and (owner is None or owner.member == branch)
        )
        batch_match = (
            workspace is not None
            and workspace.kind == "batch"
            and owner is not None
            and owner.member in workspace.members
        )
        if member_match or batch_match:
            changes.append(
                {"id": record.id, "approved": record.approval is not None, "status": record.status}
            )
    relevant = {c["id"] for c in changes}
    scoped = tuple(o for o in snapshot.observations if workspace is None or o.change_id in relevant)
    # Resolved history is retrieved with --verbose or change history; the default stays small.
    observations = [contract_mapping(o) for o in scoped if verbose or o.status != "resolved"]
    counts: dict[str, int] = {}
    for item in scoped:
        counts[item.status] = counts.get(item.status, 0) + 1
    pending = [o.observation.id for o in scoped if o.status == "pending"]
    waiting = (
        [str(item) for item in pending_admissions(repository, branch)]
        if workspace is not None and workspace.kind == "batch" and branch
        else []
    )
    receipts = []
    has_final = False
    # Evidence of an ancestor stands while only change records changed since.
    evidenced = {source}
    if workspace is not None and workspace.kind == "member":
        evidenced.update(records_only_ancestors(repository, change_root, workspace.base, source))
    for path in sorted((root / "validation").glob("*-lifecycle-*.json")):
        try:
            payload = json.loads(path.read_text())
            receipt = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
            if not receipt.valid or receipt.identity.commit not in evidenced:
                continue
            artifacts = (receipt.identity.configuration, *receipt.identity.lockfiles)
            if any(
                ArtifactIdentity.from_bytes(a.path, source_path(repository, a.path).read_bytes())
                != a
                for a in artifacts
            ):
                continue
            has_final = has_final or "final" in receipt.execution.gates
            receipts.append(
                {
                    "path": str(path),
                    "gates": list(receipt.execution.gates),
                    "source_current": not dirty,
                    "validated_at": payload.get("validated_at"),
                }
            )
        except (OSError, ValueError, KeyError, TypeError, ReceiptError):
            continue
    order = None
    approved = tuple(str(c["id"]) for c in changes if c["approved"] and c["status"] == "active")
    if (
        workspace is not None
        and workspace.kind == "member"
        and approved
        and len(approved) == len(changes)
        and not dirty
        and not merging
    ):
        try:
            order = approval_order(
                repository,
                load_manifest(repository / "signetum.toml"),
                workspace.base,
                source,
                approved,
            )
        except (ChangeError, ManifestError):
            order = None
    if merging and waiting:
        next_action = (
            f"Resolve and stage conflicts, then run batch-continue --batch {repository}; "
            "it then admits the pending members in order."
        )
    elif merging:
        next_action = (
            "Resolve and stage conflicts; use batch-continue --batch <batch> for a batch, "
            "or finish the declared member recovery."
        )
    elif workspace is None:
        next_action = "Open a registered member workspace from an exact approved base."
    elif dirty:
        next_action = "Review local changes and commit approved work before readiness."
    elif pending:
        next_action = "Resolve the pending findings through the journal."
    elif manifest_cause is not None and workspace.kind == "batch":
        next_action = (
            "This engine cannot load the batch's signetum.toml. Admit the member that migrates "
            "it; admission reads only its locations and the batch gate validates the merged "
            "manifest."
        )
    elif manifest_cause is not None:
        next_action = (
            "This engine cannot load signetum.toml. Migrate it in this member, commit and run "
            "ready; a member that keeps it cannot be readied or admitted."
        )
    elif workspace.kind == "batch":
        if has_final:
            next_action = "Inspect the generated review and explicitly authorize delivery."
        elif failed_tip(repository, branch, "final") == source:
            next_action = (
                "Final failed. Fix a defect owned by one member in that member, run ready and "
                "admit its new tip; fix a defect that appears only in the combination here in the "
                "batch; final lists it under combination repairs. For a legacy batch, "
                "commit its batch-owned approval before the fix. Then rerun final."
            )
        else:
            next_action = "Run final on this frozen batch."
    elif receipts:
        next_action = (
            "Name this member for batch admission; admission rechecks current tools and selection."
        )
    elif not changes:
        next_action = "Create one change record and obtain its exact approval."
    elif any(not c["approved"] for c in changes):
        next_action = (
            "Show the change approval view; record actual owner confirmation before implementation."
        )
    elif order is not None and not order.satisfied:
        next_action = APPROVAL_ORDER_REMEDY
    else:
        next_action = "Run ready on the committed tip; fix, commit and rerun it until it passes."
    if workspace is not None and workspace.parent and not merging and not dirty:
        # A stacked member's chain lives in its record; status only derives the next step.
        if parent_moved(repository, workspace, source):
            next_action = (
                f"Parent {workspace.parent} advanced; run maintenance workspace-sync, then ready."
            )
        elif receipts:
            order = " -> ".join(admission_order(repository, workspace.branch))
            next_action += f" Admit the chain in order {order}."
    workspaces = workspace_endings(repository)
    if git_output(repository, "rev-parse", "HEAD") != source:
        raise ValueError("source changed while reading status")
    return {
        "source": source,
        "branch": branch,
        "dirty": dirty,
        "merge_open": merging,
        "workspace": contract_mapping(workspace) if workspace else None,
        "changes": changes,
        "observations": observations,
        "observation_counts": dict(sorted(counts.items())),
        "pending": pending,
        **({"pending_admissions": waiting} if waiting else {}),
        "receipts": receipts,
        "workspaces": workspaces,
        **({"manifest": {"loadable": False, "cause": manifest_cause}} if manifest_cause else {}),
        "qualification": (
            "Recorded evidence only; tools, selection and admission are not re-executed by status."
        ),
        "next": next_action,
    }
