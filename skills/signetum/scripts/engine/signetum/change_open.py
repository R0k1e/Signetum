"""Create one draft change record in a registered implementation workspace."""

import json
import re
from pathlib import Path

from signetum.change.paths import changes_root
from signetum.change_record import parse_change_record
from signetum.git import GitError, run_git
from signetum.manifest import load_manifest
from signetum.operation_cli import OperationParser, utility_failure
from signetum.policy import delivery_policy
from signetum.source_authority import source_path
from signetum.workspaces import (
    WorkspaceError,
    branch_name,
    claim_change,
    exclude_pattern,
    read_record,
    state_root,
)


class ChangeOpenError(ValueError):
    """Authoring cannot establish a safe, owned draft destination."""


def open_change(repository: Path, name: str) -> dict[str, object]:
    if re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name) is None:
        raise ChangeOpenError("name must be lowercase kebab-case")
    repository = repository.resolve()
    try:
        branch = branch_name(repository)
        if branch == delivery_policy(repository).branch:
            raise ChangeOpenError(
                "change-open needs a member workspace; "
                "run workspace-open for a member workspace first"
            )
        try:
            workspace = read_record(state_root(repository), branch)
        except WorkspaceError as error:
            if "has no recorded base" in str(error):
                raise ChangeOpenError(
                    "change-open needs a member workspace; "
                    "run workspace-open for a member workspace first"
                ) from error
            raise
        if workspace.kind != "member":
            raise ValueError("change-open requires a registered member workspace")
        root = changes_root(load_manifest(repository / "signetum.toml"))
        relative = f"{root}/{name}/change.toml"
        path = source_path(repository, relative)
        if path.parent.exists():
            raise ValueError(f"change already exists: {root}/{name}")
        source = _draft(name, workspace.base)
        parse_change_record(source)
        claim_change(state_root(repository), name, branch)
        path.parent.mkdir(parents=True)
        try:
            with path.open("x", encoding="utf-8") as output:
                output.write(source)
        except OSError:
            path.parent.rmdir()
            raise
        return {"schema_version": 1, "status": "opened", "change": name, "files": (relative,)}
    except (OSError, ValueError, GitError, WorkspaceError) as error:
        raise ChangeOpenError(str(error)) from error


def open_batch_draft(batch: Path, task: str, base: str) -> dict[str, object]:
    """Write the batch's own unapproved change record, excluded from Git status.

    A defect that only the combination shows is fixed under this record, approved
    and committed before the fix. Left unused, it never reaches final or delivery.
    """

    name = f"batch-{task}"
    try:
        if re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name) is None:
            raise ChangeOpenError(f"batch task {task} is not a change identity")
        relative = f"{changes_root(load_manifest(batch / 'signetum.toml'))}/{name}/change.toml"
        path = source_path(batch, relative)
        if path.exists() or not run_git(batch, "cat-file", "-e", f"HEAD:{relative}").returncode:
            return {"status": "kept", "path": relative}
        source = _draft(name, base)
        parse_change_record(source)
        claim_change(state_root(batch), name, branch_name(batch))
        exclude_pattern(batch, f"/{relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            output.write(source)
    except (OSError, ValueError, GitError, WorkspaceError) as error:
        return {"status": "skipped", "cause": str(error)}
    return {
        "status": "written",
        "path": relative,
        "next": (
            "For a defect only this combination shows, fill this record, record the owner's "
            f"approval and commit it on its own with git add -f {relative} (it is excluded "
            "from Git status), then commit the fix. Left unused it is never delivered."
        ),
    }


def _draft(name: str, base: str) -> str:
    return f'''[change]
schema_version = 1
id = "{name}"

[change.source]
kind = "human_direction"
summary = "TODO record the requested outcome and relevant basis; reference retained sources."

[change.contract]
version = 1
approved_base = "{base}" # pragma: allowlist secret

[[change.contract.requirements]]
id = "REQ-001"
outcome = "TODO describe one independently verifiable outcome."
acceptance = ["TODO name observable positive and negative evidence."]

[change.contract.autonomy]
allowed = []
requires_confirmation = []

[[change.execution.steps]]
id = "STEP-001"
requirements = ["REQ-001"]
action = "TODO extend one owner; choose risk-based tests and reconcile current authorities."
'''


def main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    try:
        parsed = parser.parse_args(arguments)
        result = open_change(parsed.repository, parsed.name)
    except (ValueError, OSError) as error:
        return utility_failure("change-open", error)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
