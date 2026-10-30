"""Shared approved package inputs for real repository scenarios."""

from pathlib import Path

from signetum.change_record import contract_digest, parse_change_record
from signetum.git import git_output
from signetum.operations import AdmissionError
from signetum.workspaces import WorkspaceError, recorded_base


def approve_legacy_change(repository: Path, change_id: str = "example") -> None:
    root = repository / "changes" / change_id
    (root / "specs").mkdir(parents=True, exist_ok=True)
    (root / "plans").mkdir(parents=True, exist_ok=True)
    (root / "review.toml").write_text(f"""[review]
schema_version = 1
id = "{change_id}"
status = "approved"
[review.source]
kind = "human_direction"
summary = "Approve a fixture behavior."
[[review.clauses]]
id = "REQ-001"
statement = "The member implements the approved behavior."
disposition = "covered"
specification = "{change_id}/behavior"
""")
    (root / "specs/behavior.toml").write_text(f"""[specification]
schema_version = 1
id = "{change_id}/behavior"
version = 1
status = "approved"
implementation_authorized = true
plan = "changes/{change_id}/plans/behavior.md"
acceptance = ["The declared member check passes."]
[specification.review]
id = "{change_id}"
clauses = ["REQ-001"]
""")
    (root / "plans/behavior.md").write_text(f"""# Implement behavior
Status: approved
Specification: changes/{change_id}/specs/behavior.toml
Base: fixture
| Obligation | Clauses | Outcome |
| --- | --- | --- |
| IMPLEMENT | REQ-001 | Implement behavior and run its declared check. |
""")


def approve_change(repository: Path, change_id: str = "example") -> None:
    """Current fixtures use the same single record as ordinary development."""
    try:
        base = recorded_base(repository)
    except (WorkspaceError, AdmissionError):
        base = git_output(repository, "rev-parse", "HEAD")
    consolidated_approval(repository, base, change_id=change_id)


def commit_approval(repository: Path, change_id: str = "example") -> None:
    """Give a fixture its own committed approval before implementation."""
    approve_change(repository, change_id)
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", f"approve change {change_id}")


def consolidated_approval(
    member, base, *, approved=True, outcome="Implement the confirmed behavior.", change_id="example"
):
    text = f'''[change]
schema_version = 1
id = "{change_id}"
[change.source]
kind = "human_direction"
summary = "Implement the confirmed outcome."
[change.contract]
version = 1
approved_base = "{base}"
[[change.contract.requirements]]
id = "REQ-1"
outcome = "{outcome}"
acceptance = ["The declared member check passes."]
[[change.execution.steps]]
id = "STEP-1"
requirements = ["REQ-1"]
action = "Implement and validate the outcome."
'''
    if approved:
        digest = contract_digest(parse_change_record(text).contract)
        text += f'''[change.approval]
actor = "Owner"
recorded_at = 2026-10-29
source = "Owner confirmed the fixture outcome."
contract_digest = "{digest}"
'''
    path = member / f"changes/{change_id}/change.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def approved_record_source(source):
    record = parse_change_record(source)
    return (
        source
        + f'''[change.approval]
actor = "Owner"
recorded_at = 2026-10-29
source = "Owner confirmed the behavior."
contract_digest = "{contract_digest(record.contract)}"
'''
    )
