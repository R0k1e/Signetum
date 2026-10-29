from pathlib import Path
from shutil import copytree

import pytest

from signetum import git as git_tools
from signetum import release
from signetum.git import GitInfrastructureError, git_output
from signetum.release import ReleaseError, build_metadata, preflight


def test_release_metadata_binds_actual_component_versions_and_complete_skill(tmp_path):
    source = Path(__file__).resolve().parents[3]
    for name in ("schemas", "skills"):
        copytree(source / name, tmp_path / name)
    (tmp_path / "pyproject.toml").write_bytes((source / "pyproject.toml").read_bytes())
    before = build_metadata(tmp_path, "source-commit")
    versions = {item.name: item.version for item in before.components}
    assert versions == {"package": release.__version__, "schemas": "1", "repo-dev": "4.0.0"}
    reference = tmp_path / "skills/repo-dev/references/adoption.md"
    reference.write_text(reference.read_text() + "\nA changed adoption instruction.\n")
    after = build_metadata(tmp_path, "source-commit")
    assert before.components[1:] != after.components[1:]
    assert before.components[0] == after.components[0]


@pytest.fixture
def candidate(tmp_path):
    source = Path(__file__).resolve().parents[3]
    for name in ("schemas", "skills"):
        copytree(source / name, tmp_path / name)
    (tmp_path / "pyproject.toml").write_bytes((source / "pyproject.toml").read_bytes())
    git_output(tmp_path, "init", "-b", "engine")
    git_output(tmp_path, "config", "user.name", "Release test")
    git_output(tmp_path, "config", "user.email", "release@example.invalid")
    git_output(tmp_path, "add", ".")
    git_output(tmp_path, "commit", "-m", "delivered engine")
    tip = git_output(tmp_path, "rev-parse", "HEAD")
    git_output(tmp_path, "update-ref", "refs/remotes/origin/engine", tip)
    git_output(tmp_path, "tag", "v" + release.__version__)
    return tmp_path, tip


def test_preflight_accepts_exact_delivered_source_without_local_receipts(candidate):
    root, tip = candidate
    assert preflight(root, tip, tag="v" + release.__version__).source == tip
    (root / "later").touch()
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "later delivered source")
    git_output(root, "update-ref", "refs/remotes/origin/engine", "HEAD")
    git_output(root, "checkout", "--detach", tip)
    assert preflight(root, tip).source == tip


@pytest.mark.parametrize(
    "damage",
    [
        "source",
        "dirty",
        "unreleased",
        "tag",
        "tag-source",
        "version",
        "skill-version",
        "skill-symlink",
        "schema",
    ],
)
def test_preflight_refuses_source_or_version_mismatch(candidate, damage):
    root, tip = candidate
    tag = "v" + release.__version__
    if damage == "source":
        tip = "0" * 40
    elif damage == "dirty":
        (root / "untracked").touch()
    elif damage == "tag":
        tag = "v999.0.0"
    else:
        if damage == "version":
            p = root / "pyproject.toml"
            p.write_text(p.read_text().replace('version = "3.0.0"', 'version = "999.0.0"', 1))
        elif damage == "skill-version":
            p = root / "skills/repo-dev/SKILL.md"
            p.write_text(p.read_text().replace('version: "4.0.0"', 'version: "unknown"'))
        elif damage == "skill-symlink":
            (root / "skills/repo-dev/linked").symlink_to("SKILL.md")
        elif damage == "schema":
            (root / "schemas/release-metadata.schema.json").write_text("{}")
        else:
            (root / "new-source").touch()
        git_output(root, "add", ".")
        git_output(root, "commit", "-m", "unreleased change")
        tip = git_output(root, "rev-parse", "HEAD")
        if damage != "unreleased":
            git_output(root, "update-ref", "refs/remotes/origin/engine", tip)
        if damage in {"version", "skill-version", "skill-symlink", "schema"}:
            tag = None
    with pytest.raises(ReleaseError):
        preflight(root, tip, tag=tag)


def test_preflight_refuses_missing_git(monkeypatch, tmp_path):
    monkeypatch.setattr(git_tools, "which", lambda executable: None)
    with pytest.raises(GitInfrastructureError, match="unavailable"):
        preflight(tmp_path, "abc")
