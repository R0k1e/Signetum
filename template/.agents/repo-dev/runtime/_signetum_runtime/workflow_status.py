# Generated from signetum.workflow_status; edit the engine source and regenerate.
"""Read workflow authorities without checks, network access or another status store."""

import json
from pathlib import Path

from .change_record import parse_change_record
from .development_log import DevelopmentSnapshot
from .evidence_receipts import ArtifactIdentity, EvidenceReceipt, ReceiptError
from .git import git_output
from .serialization import contract_mapping
from .source_authority import authority_roots, source_path
from .workspaces import read_change_owner, read_record, record_path


def workflow_status(
    repository: Path, snapshot: DevelopmentSnapshot, *, source: str
) -> dict[str, object]:
    repository = repository.resolve()
    if git_output(repository, "rev-parse", "HEAD") != source:
        raise ValueError("source changed while reading status")
    branch = git_output(repository, "branch", "--show-current")
    common = Path(git_output(repository, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    root = common / "signetum"
    registered = record_path(root, branch).exists() if branch else False
    workspace = read_record(root, branch) if registered else None
    dirty = bool(git_output(repository, "status", "--porcelain"))
    merge = git_output(repository, "rev-parse", "--git-path", "MERGE_HEAD")
    merging = (
        (repository / merge).exists() if not Path(merge).is_absolute() else Path(merge).exists()
    )
    change_root, _ = authority_roots(repository)
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
    observations = [contract_mapping(o) for o in scoped]
    pending = [o.observation.id for o in scoped if o.status == "pending"]
    receipts = []
    has_final = False
    for path in sorted((root / "validation").glob("*-lifecycle-*.json")):
        try:
            payload = json.loads(path.read_text())
            receipt = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
            if not receipt.valid or receipt.identity.commit != source:
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
    if merging:
        next_action = (
            "Resolve and stage conflicts; use batch-continue for a batch, "
            "or finish the declared member recovery."
        )
    elif workspace is None:
        next_action = "Open a registered member workspace from an exact approved base."
    elif dirty:
        next_action = "Review local changes and commit approved work before readiness."
    elif pending:
        next_action = "Resolve the pending findings through the journal."
    elif workspace.kind == "batch":
        next_action = (
            "Inspect the generated review and explicitly authorize delivery."
            if has_final
            else "Run final on this frozen batch."
        )
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
    else:
        next_action = "Run targeted feedback as needed, then ready on the committed member tip."
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
        "pending": pending,
        "receipts": receipts,
        "qualification": (
            "Recorded evidence only; tools, selection and admission are not re-executed by status."
        ),
        "next": next_action,
    }
