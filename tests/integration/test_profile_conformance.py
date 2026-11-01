"""The engine binds the same explicitly resolved profile identities."""

import json
import re
from pathlib import Path

import pytest
from signetum import lifecycle, profiles
from signetum.git import git_output
from signetum.manifest import ManifestError, parse_manifest
from signetum.profiles import ProfileError
from signetum.validation.repository import configured_validation
from signetum.workspace_operations import workspace_open

ROOT = Path(__file__).parents[2]


def configuration(selected, replacements):
    text = (ROOT / "tests/fixtures/portable-python/signetum.toml").read_text()
    text = re.sub(r"^enabled = .*", "enabled = " + json.dumps(selected), text, flags=re.MULTILINE)
    if replacements:
        text += "\n[profiles.replacements]\n" + "\n".join(
            f"{json.dumps(target)} = {json.dumps(replacement)}"
            for target, replacement in replacements.items()
        )
    return text


@pytest.mark.parametrize(
    "selected,replacements,expected",
    [
        ([], {}, ()),
        (["python-existing@1"], {}, ("python-existing@1", "shared-core@1")),
        (["node-existing@1"], {}, ("node-existing@1", "shared-core@1")),
        (["rust-existing@1"], {}, ("rust-existing@1", "shared-core@1")),
        (
            ["python-existing@1", "node-existing@1", "rust-existing@1"],
            {},
            ("node-existing@1", "python-existing@1", "rust-existing@1", "shared-core@1"),
        ),
        (["python-default@1"], {}, ("python-default@1", "shared-core@1")),
        (["git-worktrunk@1"], {}, ("git-worktrunk@1", "shared-core@1")),
        (
            ["python-default@1", "git-worktrunk@1"],
            {},
            ("git-worktrunk@1", "python-default@1", "shared-core@1"),
        ),
        (
            ["python-default@1"],
            {"python-default@1": "git-worktrunk@1"},
            ("git-worktrunk@1", "shared-core@1"),
        ),
    ],
)
def test_native_frontends_resolve_dependency_and_replacement_identities(
    selected, replacements, expected
):
    text = configuration(selected, replacements)
    _, installed = configured_validation(parse_manifest(text))
    assert installed.profiles == expected


@pytest.mark.parametrize(
    "selected,replacements",
    [
        (["unsupported@1"], {}),
        (["python-default@1"], {"git-worktrunk@1": "python-default@1"}),
        (["python-default@1"], {"python-default@1": "unsupported@1"}),
        (["python-default@1"], {"python-default@1": "python-default@1"}),
        (["python-default@1", "python-default@1"], {}),
    ],
)
def test_both_frontends_refuse_unsupported_or_ambiguous_profile_selection(selected, replacements):
    text = configuration(selected, replacements)
    with pytest.raises((ProfileError, ManifestError)):
        configured_validation(parse_manifest(text))


@pytest.mark.parametrize("missing_catalog", [False, True])
def test_lifecycle_reports_profile_failure_as_one_operation(
    repository, monkeypatch, capsys, tmp_path, missing_catalog
):
    root, _ = repository
    opened = workspace_open(root, "plan/profiles", git_output(root, "rev-parse", "HEAD"))
    member = Path(str(opened["worktree"]))
    manifest = member / "signetum.toml"
    manifest.write_text(manifest.read_text() + '\n[profiles]\nenabled = ["unsupported@1"]\n')
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "select unsupported profile")
    monkeypatch.chdir(member)
    capsys.readouterr()
    if missing_catalog:
        monkeypatch.setattr(profiles, "files", lambda _: tmp_path / "unavailable-catalog")
    assert lifecycle.main(["changed", "--explain"]) == (4 if missing_catalog else 2)
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == ("infrastructure_error" if missing_catalog else "invalid")
    expected = "profile resource unavailable" if missing_catalog else "unsupported profile"
    assert expected in json.dumps(payload)
    assert "Traceback" not in output.err
