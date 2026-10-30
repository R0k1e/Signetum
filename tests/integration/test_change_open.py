"""New authoring creates one unapproved record in the declared member workspace."""

import importlib
from pathlib import Path

import pytest

from signetum.change_record import parse_change_record
from signetum.git import git_output
from signetum.workspaces import WorkspaceRecord, state_root, write_record


@pytest.fixture(params=["signetum", "_signetum_runtime"])
def author(request, monkeypatch):
    if request.param == "_signetum_runtime":
        monkeypatch.syspath_prepend(
            str(
                Path(__file__).parents[2]
                / "tests/fixtures/portable-python/.agents/signetum/runtime"
            )
        )
    return importlib.import_module(request.param + ".change_open")


def test_open_uses_registered_base_and_creates_one_draft_without_approval(repository, author):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    git_output(root, "switch", "-c", "plan/author")
    write_record(state_root(root), WorkspaceRecord(1, "plan/author", base, "member"))
    git_output(root, "commit", "--allow-empty", "-m", "discovery after the recorded base")
    assert git_output(root, "rev-parse", "HEAD") != base
    result = author.open_change(root, "first-change")
    assert result["files"] == ("changes/first-change/change.toml",)
    record = parse_change_record((root / result["files"][0]).read_text())
    assert record.id == "first-change" and record.approval is None
    assert record.contract.approved_base == base
    assert len(list((root / "changes/first-change").rglob("*"))) == 1
    with pytest.raises(author.ChangeOpenError, match="already exists"):
        author.open_change(root, "first-change")


@pytest.mark.parametrize("damage", ["unregistered", "batch", "unsafe-name", "symlink", "delivery"])
def test_open_refuses_unowned_or_unsafe_targets_without_creating_files(repository, author, damage):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    branch = "main" if damage == "delivery" else "plan/refusal"
    if damage != "delivery":
        git_output(root, "switch", "-c", branch)
    if damage != "unregistered":
        write_record(
            state_root(root),
            WorkspaceRecord(1, branch, base, "batch" if damage == "batch" else "member"),
        )
    if damage == "symlink":
        destination = root.parent / "foreign"
        destination.mkdir()
        (root / "changes").symlink_to(destination, target_is_directory=True)
    with pytest.raises(author.ChangeOpenError):
        author.open_change(root, "../unsafe" if damage == "unsafe-name" else "first-change")
    assert not (root / "changes/first-change").exists()
