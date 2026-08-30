"""Validate the copied Review, Specification, and Plan ownership graph."""

from __future__ import annotations

import argparse
import json
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    detail: str


def validate(repository: Path, changes_root: str) -> tuple[Issue, ...]:
    root = repository.resolve()
    changes = root / changes_root
    issues: list[Issue] = []
    clauses: dict[tuple[str, str], dict[str, Any]] = {}
    specifications: dict[str, dict[str, Any]] = {}
    owners: dict[tuple[str, str], list[str]] = defaultdict(list)

    if not changes.is_dir():
        return (Issue("missing-changes-root", changes_root, "configured root is absent"),)

    for change in sorted(path for path in changes.iterdir() if path.is_dir()):
        review_path = change / "review.toml"
        review = _load_contract(root, review_path, "review", issues)
        if review is None:
            continue
        review_id = review.get("id")
        if not isinstance(review_id, str) or not review_id:
            issues.append(_issue(root, "invalid-review-id", review_path, "review.id is required"))
            continue
        review_clauses = review.get("clauses")
        if not isinstance(review_clauses, list) or not review_clauses:
            issues.append(
                _issue(root, "missing-review-clauses", review_path, "clauses are required")
            )
            continue
        for clause in review_clauses:
            if not isinstance(clause, dict) or not isinstance(clause.get("id"), str):
                issues.append(
                    _issue(root, "invalid-review-clause", review_path, "clause.id is required")
                )
                continue
            key = (review_id, clause["id"])
            if key in clauses:
                issues.append(_issue(root, "duplicate-review-clause", review_path, clause["id"]))
            else:
                clauses[key] = {**clause, "path": review_path, "review": review}

        specs_root = change / "specs"
        for spec_path in sorted(specs_root.glob("*.toml")) if specs_root.is_dir() else ():
            spec = _load_contract(root, spec_path, "specification", issues)
            if spec is None:
                continue
            spec_id = spec.get("id")
            if not isinstance(spec_id, str) or not spec_id:
                issues.append(_issue(root, "invalid-specification-id", spec_path, "id is required"))
                continue
            if spec_id in specifications:
                issues.append(_issue(root, "duplicate-specification", spec_path, spec_id))
                continue
            spec["path"] = spec_path
            specifications[spec_id] = spec

    for spec_id, spec in specifications.items():
        spec_path = spec["path"]
        review_ref = spec.get("review")
        review_id = review_ref.get("id") if isinstance(review_ref, dict) else None
        clause_ids = review_ref.get("clauses") if isinstance(review_ref, dict) else None
        if not isinstance(review_id, str) or not isinstance(clause_ids, list):
            issues.append(_issue(root, "invalid-specification-review", spec_path, spec_id))
            continue
        plan_value = spec.get("plan")
        plan_path = _repository_path(root, plan_value)
        plan_content: str | None = None
        if plan_path is None or not plan_path.is_file():
            issues.append(_issue(root, "missing-plan", spec_path, str(plan_value)))
        else:
            plan_content = plan_path.read_text(encoding="utf-8")
        for clause_id in clause_ids:
            key = (review_id, clause_id) if isinstance(clause_id, str) else None
            if key is None or key not in clauses:
                issues.append(_issue(root, "unknown-review-clause", spec_path, str(clause_id)))
                continue
            owners[key].append(spec_id)
            if (
                plan_content is not None
                and plan_path is not None
                and clause_id not in plan_content
            ):
                issues.append(_issue(root, "plan-missing-clause", plan_path, clause_id))

    for key, clause in clauses.items():
        disposition = clause.get("disposition")
        specification = clause.get("specification")
        clause_owners = owners.get(key, [])
        if len(clause_owners) > 1:
            issues.append(_issue(root, "duplicate-clause-owner", clause["path"], key[1]))
        if disposition in {"covered", "deferred"}:
            if not isinstance(specification, str) or specification not in specifications:
                issues.append(
                    _issue(root, "missing-specification", clause["path"], str(specification))
                )
            elif specification not in clause_owners:
                issues.append(_issue(root, "ownership-mismatch", clause["path"], key[1]))
            if disposition == "deferred" and _is_complete(clause["review"]):
                issues.append(_issue(root, "unresolved-deferral", clause["path"], key[1]))
        elif disposition == "out_of_scope":
            if not isinstance(clause.get("reason"), str) or not clause["reason"].strip():
                issues.append(_issue(root, "missing-out-of-scope-reason", clause["path"], key[1]))
            if clause_owners:
                issues.append(_issue(root, "out-of-scope-owned", clause["path"], key[1]))
        else:
            issues.append(_issue(root, "invalid-disposition", clause["path"], key[1]))

    return tuple(sorted(issues, key=lambda item: (item.path, item.code, item.detail)))


def _load_contract(
    root: Path, path: Path, section: str, issues: list[Issue]
) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append(_issue(root, f"missing-{section}", path, "required contract is absent"))
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        issues.append(_issue(root, "invalid-toml", path, str(error)))
        return None
    contract = data.get(section)
    if not isinstance(contract, dict):
        issues.append(_issue(root, f"missing-{section}-section", path, section))
        return None
    return contract


def _repository_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    candidate = (root / value).resolve()
    return candidate if candidate.is_relative_to(root) else None


def _is_complete(review: dict[str, Any]) -> bool:
    acceptance = review.get("acceptance")
    result = acceptance.get("result") if isinstance(acceptance, dict) else None
    return review.get("status") in {"complete", "completed"} or result == "accepted"


def _issue(root: Path, code: str, path: Path, detail: str) -> Issue:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        relative = path
    return Issue(code, relative.as_posix(), detail)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--changes-root", default="changes")
    arguments = parser.parse_args()
    issues = validate(arguments.repository, arguments.changes_root)
    print(
        json.dumps(
            {
                "issues": [issue.__dict__ for issue in issues],
                "schema_version": 1,
                "valid": not issues,
            },
            sort_keys=True,
        )
    )
    return 0 if not issues else 3


if __name__ == "__main__":
    raise SystemExit(main())
