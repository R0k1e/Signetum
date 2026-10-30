"""Boundary parsing for Review, Specification, and Markdown Plan documents."""

from pathlib import Path

from signetum.change.models import (
    Decision,
    DecisionStatus,
)

_DECISION_FIELDS = {
    "status": "status",
    "supersedes": "supersedes",
    "superseded by": "superseded_by",
    "partially supersedes": "partially_supersedes",
}


def parse_decision(text: str, relative: str) -> Decision:
    """Read what one decision file declares about its own standing."""

    fields: dict[str, list[str]] = {
        "supersedes": [],
        "superseded_by": [],
        "partially_supersedes": [],
    }
    status = "proposed"
    for line in text.splitlines():
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
        partially_supersedes=tuple(fields["partially_supersedes"]),
    )


def load_decision(path: Path, relative: str) -> Decision:
    return parse_decision(path.read_text(encoding="utf-8"), relative)
