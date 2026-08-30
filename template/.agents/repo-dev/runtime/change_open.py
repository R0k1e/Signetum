"""Create one new active Change without overwriting repository content."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


class ChangeOpenError(ValueError):
    """A requested Change identity is unsafe or already owned."""


def open_change(repository: Path, name: str) -> dict[str, object]:
    """Create a draft Review, Specification, and Plan for one safe identity."""
    if re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name) is None:
        raise ChangeOpenError("name must be lowercase kebab-case")
    root = repository.resolve()
    target = root / "changes" / name
    if target.exists():
        raise ChangeOpenError(f"change already exists: changes/{name}")

    specification = target / "specs" / "change.yaml"
    plan = target / "plans" / "change.md"
    specification.parent.mkdir(parents=True)
    plan.parent.mkdir()
    review = target / "review.yaml"
    review.write_text(_review(name), encoding="utf-8")
    specification.write_text(_specification(name), encoding="utf-8")
    plan.write_text(_plan(name), encoding="utf-8")
    return {
        "change": name,
        "files": tuple(str(path.relative_to(root)) for path in (review, specification, plan)),
        "schema_version": 1,
        "status": "opened",
    }


def _review(name: str) -> str:
    return f"""review:
  schema_version: 1
  id: {name}
  status: draft
  source:
    kind: human_direction
    summary: TODO
  clauses:
    - id: REQ-001
      statement: TODO describe one independently verifiable need.
  acceptance:
    result: pending
    delivery_commit: null
    accepted_clauses: []
    rejected_clauses: []
"""


def _specification(name: str) -> str:
    return f"""specification:
  schema_version: 1
  id: {name}/change
  version: 1
  status: draft
  implementation_authorized: false
  review:
    id: {name}
    clauses: [REQ-001]
  decisions: []
  plan: changes/{name}/plans/change.md
  acceptance:
    - TODO describe observable behavior.
"""


def _plan(name: str) -> str:
    return f"""# {name} plan

Status: draft
Specification: `changes/{name}/specs/change.yaml`
Base: TODO

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| CHANGE-01 | REQ-001 | TODO map the clause to implementation and behavioral evidence. |
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    arguments = parser.parse_args()
    try:
        result = open_change(Path.cwd(), arguments.name)
    except ChangeOpenError as error:
        print(json.dumps({"reason": str(error), "status": "refused"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
