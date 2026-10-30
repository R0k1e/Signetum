import json
from pathlib import Path

import pytest
from jsonschema import validate

from signetum import git as git_tools
from signetum import release
from signetum.git import GitInfrastructureError, git_output
from signetum.release import ReleaseError, build_metadata, preflight


@pytest.fixture
def components(tmp_path):
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas/release-metadata.schema.json").write_text(
        '{"properties":{"schema_version":{"const":2}}}'
    )
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname="signetum"\nversion="{release.__version__}"\n'
    )
    skill = tmp_path / "skills/signetum"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: signetum\ndescription: Fixture\nmetadata:\n"
        f'  version: "{release.__version__}"\n---\n'
    )
    (skill / "references/adoption.md").write_text("Fixture adoption basis.\n")
    policy = tmp_path / ".agents/repo-dev/repo.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("delivery:\n  branch: main\n")
    return tmp_path


def test_release_metadata_binds_versions_and_complete_skill(components):
    source = Path(__file__).resolve().parents[3]
    schema = json.loads((source / "schemas/release-metadata.schema.json").read_text())
    validate(build_metadata(source, "source-commit").model_dump(mode="json"), schema)
    duplicated = build_metadata(source, "source-commit").model_dump(mode="json")
    duplicated["components"] = [duplicated["components"][0]] * 3
    with pytest.raises(ValueError):
        release.ReleaseMetadata.model_validate(duplicated)
    before = build_metadata(components, "source-commit")
    versions = {item.name: item.version for item in before.components}
    assert versions == {
        "package": release.__version__,
        "schemas": "2",
        "signetum-skill": release.__version__,
    }
    reference = components / "skills/signetum/references/adoption.md"
    reference.write_text(reference.read_text() + "Changed adoption basis.\n")
    after = build_metadata(components, "source-commit")
    assert before.components[1] != after.components[1]
    assert before.components[0] == after.components[0]
    assert before.components[2] == after.components[2]


@pytest.mark.parametrize("damage", ["package-version", "skill-version", "skill-symlink", "schema"])
def test_component_refusals_need_no_repository(components, damage):
    if damage == "package-version":
        p = components / "pyproject.toml"
        p.write_text(p.read_text().replace(release.__version__, "999.0.0"))
    elif damage == "skill-version":
        p = components / "skills/signetum/SKILL.md"
        p.write_text(
            p.read_text().replace(f'version: "{release.__version__}"', 'version: "999.0.0"')
        )
    elif damage == "skill-symlink":
        (components / "skills/signetum/linked").symlink_to("SKILL.md")
    else:
        (components / "schemas/release-metadata.schema.json").write_text("{}")
    with pytest.raises(ReleaseError):
        build_metadata(components, "source-commit")


@pytest.fixture
def candidate(components):
    root = components
    git_output(root, "init", "-b", "main")
    git_output(root, "config", "user.name", "Release test")
    git_output(root, "config", "user.email", "release@example.invalid")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "delivered product")
    tip = git_output(root, "rev-parse", "HEAD")
    git_output(root, "update-ref", "refs/remotes/origin/main", tip)
    git_output(root, "tag", "v" + release.__version__)
    return root, tip


def test_preflight_accepts_exact_delivered_source_without_local_receipts(candidate):
    root, tip = candidate
    assert preflight(root, tip, tag="v" + release.__version__).source == tip
    (root / "later").touch()
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "later delivered source")
    git_output(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git_output(root, "checkout", "--detach", tip)
    assert preflight(root, tip).source == tip


@pytest.mark.parametrize("damage", ["source", "dirty", "unreleased", "tag", "tag-source"])
def test_preflight_refuses_source_or_tag_mismatch(candidate, damage):
    root, tip = candidate
    tag = "v" + release.__version__
    if damage == "source":
        tip = "0" * 40
    elif damage == "dirty":
        (root / "untracked").touch()
    elif damage == "tag":
        tag = "v999.0.0"
    else:
        (root / "new-source").touch()
        git_output(root, "add", ".")
        git_output(root, "commit", "-m", "new source")
        tip = git_output(root, "rev-parse", "HEAD")
        if damage == "tag-source":
            git_output(root, "update-ref", "refs/remotes/origin/main", tip)
    with pytest.raises(ReleaseError):
        preflight(root, tip, tag=tag)


def test_preflight_refuses_missing_git(monkeypatch, tmp_path):
    monkeypatch.setattr(git_tools, "which", lambda executable: None)
    with pytest.raises(GitInfrastructureError, match="unavailable"):
        preflight(tmp_path, "abc")
