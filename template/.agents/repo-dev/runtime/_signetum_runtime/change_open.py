# Generated from signetum.change_open; edit the engine source and regenerate.
"""Create one draft change record in a registered implementation workspace."""

import argparse
import json
import re
from pathlib import Path

from .change_paths import changes_root
from .change_record import parse_change_record
from .git import GitError
from .manifest import load_manifest
from .policy import delivery_policy
from .source_authority import source_path
from .workspaces import WorkspaceError, branch_name, claim_change, read_record, state_root


class ChangeOpenError(ValueError):
    """Authoring cannot establish a safe, owned draft destination."""


def open_change(repository: Path, name: str) -> dict[str, object]:
    if re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name) is None:
        raise ChangeOpenError("name must be lowercase kebab-case")
    repository = repository.resolve()
    try:
        branch = branch_name(repository)
        workspace = read_record(state_root(repository), branch)
        if workspace.kind != "member":
            raise ValueError("change-open requires a registered member workspace")
        if branch == delivery_policy(repository).branch:
            raise ValueError("change-open refuses the delivery workspace")
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


def _draft(name: str, base: str) -> str:
    return f'''[change]
schema_version = 1
id = "{name}"

[change.source]
kind = "human_direction"
summary = "TODO record the original intent and relevant context."

[change.contract]
version = 1
approved_base = "{base}"

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
action = "TODO extend the existing owner and verify the outcome."
'''


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parsed = parser.parse_args(arguments)
    try:
        result = open_change(parsed.repository, parsed.name)
    except ChangeOpenError as error:
        print(json.dumps({"status": "refused", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
