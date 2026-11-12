"""Decision identity requires an explicit move bound to committed history."""

import json

import pytest
from signetum import lifecycle, maintenance
from signetum import operation_records as records
from signetum.decision_identity import numbered_targets
from signetum.git import git_output
from signetum.operations import AdmissionError
from signetum.workspaces import state_root


def _number(root, declared=None):
    old = "docs/decisions/ADP-proposal-new.md"
    new = "docs/decisions/ADP-0001-new.md"
    (root / old).parent.mkdir(parents=True)
    (root / old).write_text("# New\nStatus: Accepted\n")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "accepted decision")
    proposal = git_output(root, "rev-parse", "HEAD")
    git_output(root, "mv", old, new)
    entry = json.dumps([old, new])
    body = f"Signetum-Decision-Base: {declared or proposal}\nSignetum-Decision-Rename: {entry}"
    git_output(root, "commit", "-m", "number decision", "-m", body)
    return proposal, git_output(root, "rev-parse", "HEAD"), old, new


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
    old = "docs/decisions/ADP-proposal-new.md"
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
        entry = json.dumps(["../ADP-proposal-new.md", "../ADP-0001-new.md"])
    declared = "f" * 40 if case == "wrong_base" else base
    body = f"Signetum-Decision-Base: {declared}\nSignetum-Decision-Rename: {entry}"
    if case == "repeated":
        body += f"\nSignetum-Decision-Rename: {entry}"
    git_output(root, "commit", "--allow-empty", "-m", "number decision", "-m", body)
    with pytest.raises(AdmissionError, match="decision identity"):
        numbered_targets(root, base, "HEAD", "docs/decisions")


def test_structured_mapping_binds_the_human_commit(repository, monkeypatch, capsys, tmp_path):
    root, _ = repository
    old = "docs/decisions/ADP-proposal-new.md"
    new = "docs/decisions/ADP-0001-new.md"
    (root / old).parent.mkdir(parents=True)
    (root / old).write_text("# New\nStatus: Accepted\n")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "accepted decision")
    base = git_output(root, "rev-parse", "HEAD")
    git_output(root, "mv", old, new)
    git_output(root, "commit", "-m", "Number the accepted decision.")
    commit = git_output(root, "rev-parse", "HEAD")
    message = records.commit_message(root, commit)
    assert "Signetum-" not in message
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("This is not the numbering commit.\n", encoding="utf-8")
    monkeypatch.chdir(root)
    capsys.readouterr()
    code = maintenance.main(
        [
            "record-decision-mapping",
            "--commit",
            commit,
            "--base",
            base,
            "--directory",
            "docs/decisions",
            "--message-file",
            str(wrong),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "does not match the commit" in captured.out + captured.err
    assert not list((state_root(root) / "operations" / "records").glob("*.json"))

    exact = tmp_path / "message.txt"
    exact.write_text(message, encoding="utf-8")
    code = maintenance.main(
        [
            "record-decision-mapping",
            "--commit",
            commit,
            "--base",
            base,
            "--directory",
            "docs/decisions",
            "--message-file",
            str(exact),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert numbered_targets(root, base, "HEAD", "docs/decisions") == {old: new}
    document = records.load_index(root).for_commit(commit)
    assert document is not None
    assert document["kind"] == "decision-mapping"
    assert document["source"] == commit
    assert document["attested_base"] == base
    assert document["mappings"] == [[old, new]]
    assert git_output(root, "rev-parse", "HEAD") == commit

    commit_file_name = root / "later.txt"
    commit_file_name.write_text("later\n")
    git_output(root, "add", "later.txt")
    git_output(root, "commit", "-m", "continue after numbering")
    with pytest.raises(AdmissionError, match="cannot include a structured operation"):
        records.adopt_legacy_history(root, ["HEAD"])


def test_legacy_numbering_trailers_apply_only_after_adoption(repository):
    root, _ = repository
    initial = git_output(root, "rev-parse", "HEAD")
    proposal, commit, old, new = _number(root)
    with pytest.raises(AdmissionError, match="structured operation or legacy history"):
        numbered_targets(root, proposal, commit, "docs/decisions")
    lifecycle._require_numbering_base(root, initial, commit)

    records.adopt_legacy_history(root, [commit])
    assert numbered_targets(root, proposal, commit, "docs/decisions") == {old: new}
    with pytest.raises(AdmissionError, match="do not bind the batch base"):
        numbered_targets(root, initial, commit, "docs/decisions")
    lifecycle._require_numbering_base(root, proposal, commit)
    with pytest.raises(AdmissionError, match="decision numbering is bound to a different"):
        lifecycle._require_numbering_base(root, initial, commit)
    git_output(root, "commit", "--allow-empty", "-m", "after the adopted numbering")
    with pytest.raises(AdmissionError, match="cannot expand"):
        records.adopt_legacy_history(root, ["HEAD"])
