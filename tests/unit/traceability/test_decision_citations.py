"""A citation is checked for what it obtained, not for how it is spelled."""

from pathlib import Path

import pytest

from reposeal.change.models import Decision, DecisionStatus
from reposeal.traceability.loading import load_decision
from reposeal.traceability.validator import decision_corpus_issues

HEADER = """# A decision

Status: {status}
Review date: 2026-09-02
Supersedes: {supersedes}
Superseded by: {superseded_by}
"""


def _write(tmp_path: Path, name: str, **fields: str) -> Decision:
    values = {"status": "Accepted", "supersedes": "None", "superseded_by": "None"}
    values.update(fields)
    path = tmp_path / name
    path.write_text(HEADER.format(**values), encoding="utf-8")
    return load_decision(path, f"docs/decisions/{name}")


def test_a_decision_reports_the_standing_it_declares(tmp_path: Path) -> None:
    decision = _write(tmp_path, "ADP-one.md", status="Proposed", supersedes="ADP-two.md")

    assert decision.status is DecisionStatus.PROPOSED
    assert decision.supersedes == ("ADP-two.md",)
    assert decision.superseded_by == ()
    assert decision.name == "ADP-one.md"


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("Accepted", DecisionStatus.ACCEPTED),
        ("Proposed", DecisionStatus.PROPOSED),
        ("Rejected", DecisionStatus.REJECTED),
        ("Withdrawn pending review", DecisionStatus.DRAFT),
    ],
)
def test_an_unrecognised_status_is_not_read_as_accepted(
    tmp_path: Path, declared: str, expected: DecisionStatus
) -> None:
    assert _write(tmp_path, "ADP-one.md", status=declared).status is expected


def test_a_supersession_recorded_on_both_sides_is_accepted(tmp_path: Path) -> None:
    successor = _write(tmp_path, "ADP-0002-new.md", supersedes="ADP-old.md")
    replaced = _write(tmp_path, "ADP-old.md", superseded_by="ADP-0002-new.md")

    issues = decision_corpus_issues(((successor.path, successor), (replaced.path, replaced)))

    assert issues == ()


def test_a_supersession_recorded_on_one_side_is_refused(tmp_path: Path) -> None:
    successor = _write(tmp_path, "ADP-0002-new.md", supersedes="ADP-old.md")
    replaced = _write(tmp_path, "ADP-old.md")

    issues = decision_corpus_issues(((successor.path, successor), (replaced.path, replaced)))

    assert [issue.code for issue in issues] == ["one-sided-supersession"]
    assert issues[0].file == "docs/decisions/ADP-old.md"
    assert "ADP-0002-new.md" in issues[0].reason


def test_superseding_an_absent_decision_is_refused(tmp_path: Path) -> None:
    successor = _write(tmp_path, "ADP-0002-new.md", supersedes="ADP-missing.md")

    issues = decision_corpus_issues(((successor.path, successor),))

    assert [issue.code for issue in issues] == ["dangling-supersession"]
