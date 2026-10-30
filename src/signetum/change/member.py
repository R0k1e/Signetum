"""Qualify one approved implementation and its immutable workspace ownership."""

from pathlib import Path

from signetum.change.scope import ChangeError, member_scope, require_member_changes
from signetum.manifest import RepositoryManifest
from signetum.operations import AdmissionError
from signetum.workspaces import WorkspaceError, branch_name, claim_change, read_record, state_root


def qualify_member(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str, *, operation: str = "ready"
) -> tuple[str, ...]:
    branch = branch_name(repository)
    if read_record(state_root(repository), branch).kind != "member":
        raise AdmissionError(f"{operation} requires a registered member workspace")
    try:
        carried = require_member_changes(repository, manifest, base, tip)
        for change_id in member_scope(repository, manifest, base, tip).first_delivered:
            claim_change(state_root(repository), change_id, branch)
    except (ChangeError, WorkspaceError) as error:
        raise AdmissionError(str(error)) from error
    return carried
