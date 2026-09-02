"""Boundary parsing for Review, Specification, and Markdown Plan documents."""

import re
import tomllib
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from reposeal.change.models import (
    Decision,
    DecisionStatus,
    Plan,
    Review,
    Specification,
)

_MAPPING = TypeAdapter(dict[str, object])
_TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")


def _mapping(document: object, key: str) -> dict[str, object]:
    outer = _MAPPING.validate_python(document)
    return _MAPPING.validate_python(outer[key])


def load_review(path: Path) -> Review:
    raw = _mapping(tomllib.loads(path.read_text(encoding="utf-8")), "review")
    return Review.model_validate(raw, strict=False)


def load_specification(path: Path) -> Specification:
    raw = _mapping(tomllib.loads(path.read_text(encoding="utf-8")), "specification")
    known = set(Specification.model_fields)
    extensions = {key: value for key, value in raw.items() if key not in known}
    normalized = {key: value for key, value in raw.items() if key in known}
    normalized["extensions"] = extensions
    return Specification.model_validate(normalized, strict=False)


_DECISION_FIELDS = {
    "status": "status",
    "supersedes": "supersedes",
    "superseded by": "superseded_by",
}


def load_decision(path: Path, relative: str) -> Decision:
    """Read what one decision file declares about its own standing."""

    fields: dict[str, list[str]] = {"supersedes": [], "superseded_by": []}
    status = "proposed"
    for line in path.read_text(encoding="utf-8").splitlines():
        label, separator, value = line.partition(":")
        if not separator:
            continue
        key = _DECISION_FIELDS.get(label.strip().lower())
        if key is None:
            continue
        entries = [item.strip() for item in value.split(",") if item.strip()]
        if key == "status":
            status = value.strip().lower() or "proposed"
        else:
            fields[key] = [item for item in entries if item.lower() != "none"]
    known = {item.value for item in DecisionStatus}
    return Decision(
        path=relative,
        status=DecisionStatus(status if status in known else "draft"),
        supersedes=tuple(fields["supersedes"]),
        superseded_by=tuple(fields["superseded_by"]),
    )


def load_plan(path: Path, change_id: str) -> Plan:
    text = path.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    obligations: list[dict[str, object]] = []
    in_obligations = False
    for line in text.splitlines():
        if line.startswith("Status:"):
            declared_status = line.partition(":")[2].strip().lower()
            if declared_status.startswith("approved"):
                fields["status"] = "approved"
            elif declared_status.startswith(("draft", "future", "blocked")):
                fields["status"] = "draft"
            else:
                fields["status"] = declared_status
        elif line.startswith("Specification:"):
            fields["specification"] = line.partition(":")[2].strip().strip("`")
        elif line.startswith("Base:"):
            fields["approved_base"] = line.partition(":")[2].strip().strip("`")
        elif line.startswith("## "):
            in_obligations = line.strip() == "## Obligations"
        elif line.startswith("| Obligation | Clauses | Outcome |"):
            in_obligations = True
        elif in_obligations and (match := _TABLE_ROW.match(line)):
            obligation_id, clauses, outcome = (item.strip() for item in match.groups())
            if obligation_id not in {"ID", "---"} and not obligation_id.startswith("-"):
                obligations.append(
                    {
                        "id": obligation_id,
                        "clauses": tuple(item.strip() for item in clauses.split(",")),
                        "outcome": outcome,
                    }
                )
    try:
        return Plan.model_validate(
            {
                "id": f"{change_id}/{path.stem}",
                "status": fields["status"],
                "specification": fields["specification"],
                "approved_base": fields["approved_base"],
                "obligations": obligations,
            },
            strict=False,
        )
    except (KeyError, ValidationError) as error:
        raise ValueError(f"invalid Plan document: {path}") from error
