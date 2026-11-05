"""Qualify one approved implementation and its immutable workspace ownership."""

from pathlib import Path

from signetum.change.scope import member_scope
from signetum.manifest import RepositoryManifest
from signetum.operations import AdmissionError
from signetum.source_admission import require_source_admission
from signetum.workspaces import WorkspaceError, branch_name, claim_change, read_record, state_root


def qualify_member(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str, *, operation: str = "ready"
) -> tuple[str, ...]:
    branch = branch_name(repository)
    if read_record(state_root(repository), branch).kind != "member":
        raise AdmissionError(f"{operation} requires a registered member workspace")
    try:
        carried = require_source_admission(repository, manifest, base, tip, member=True)
        for change_id in member_scope(repository, manifest, base, tip).first_delivered:
            claim_change(state_root(repository), change_id, branch)
    except WorkspaceError as error:
        raise AdmissionError(str(error)) from error
    return carried
