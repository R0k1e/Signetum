"""Shared approved package inputs for real repository scenarios."""

from pathlib import Path


def approve_change(repository: Path, change_id: str = "example") -> None:
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
