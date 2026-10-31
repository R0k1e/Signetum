"""Independent template queries use the engine's complete change authority."""

from pathlib import Path

import pytest
from signetum.git import git_output
from signetum.traceability.boundary import GitInventoryProvider

ROOT = Path(__file__).parents[2]


def test_inventory_cannot_be_redirected_to_a_foreign_repository(tmp_path, monkeypatch):
    root, foreign = tmp_path / "own", tmp_path / "foreign"
    for path, name in ((root, "own.txt"), (foreign, "foreign.txt")):
        path.mkdir()
        git_output(path, "init", "-b", "main")
        (path / name).write_text("tracked")
        git_output(path, "add", name)
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))
    observed = sorted(GitInventoryProvider().read(root).paths)
    assert observed == ["own.txt"]


@pytest.fixture(name="repository")
def local_only_repository(local_repository):
    return local_repository
