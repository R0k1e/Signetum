"""Decision identity requires an explicit move bound to committed history."""

import json

import pytest

from signetum.decision_identity import numbered_targets
from signetum.git import git_output
from signetum.operations import AdmissionError


@pytest.mark.parametrize(
    "case",
    [
        "malformed",
        "not_pair",
        "different_slug",
        "outside",
        "missing_move",
        "wrong_base",
        "repeated",
    ],
)
def test_invalid_numbering_provenance_is_refused(repository, case):
    root, _ = repository
    old = "docs/decisions/ADP-new.md"
    new = "docs/decisions/ADP-0001-new.md"
    (root / old).parent.mkdir(parents=True)
    (root / old).write_text("# New\nStatus: Accepted\n")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "accepted decision")
    base = git_output(root, "rev-parse", "HEAD")
    if case != "missing_move":
        git_output(root, "mv", old, new)
    entry = json.dumps([old, new])
    if case == "malformed":
        entry = "not json"
    elif case == "not_pair":
        entry = "{}"
    elif case == "different_slug":
        entry = json.dumps([old, "docs/decisions/ADP-0001-other.md"])
    elif case == "outside":
        entry = json.dumps(["../ADP-new.md", "../ADP-0001-new.md"])
    declared = "f" * 40 if case == "wrong_base" else base
    body = f"Signetum-Decision-Base: {declared}\nSignetum-Decision-Rename: {entry}"
    if case == "repeated":
        body += f"\nSignetum-Decision-Rename: {entry}"
    git_output(root, "commit", "--allow-empty", "-m", "number decision", "-m", body)
    with pytest.raises(AdmissionError, match="decision identity"):
        numbered_targets(root, base, "HEAD", "docs/decisions")
