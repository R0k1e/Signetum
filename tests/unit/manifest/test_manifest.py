from pathlib import Path

import pytest

from reposeal.manifest import ManifestError, load_manifest

FIXTURE = Path(__file__).parents[2] / "fixtures" / "reposeal.toml"


def test_load_manifest_preserves_language_neutral_repository_facts() -> None:
    manifest = load_manifest(FIXTURE)

    assert manifest.schema_version == 2
    assert manifest.reposeal.protocol == 2
    assert manifest.reposeal.template_version == "0.2.0"
    assert manifest.repository.architecture == "docs/ARCHITECTURE.md"
    assert manifest.profiles.enabled == ("python-default@1", "git-worktrunk@1")
    assert manifest.impact.rules[0].gates == ("python.type", "python.unit")


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [
        ("reposeal.toml", "schema_version = 1\n", "unsupported manifest schema: 1"),
        ("repository.toml", "schema_version = 2\n", "must be named reposeal.toml"),
        (
            "reposeal.toml",
            """schema_version = 2
[reposeal]
protocol = 2
template_version = "main"
[repository]
architecture = "docs/ARCHITECTURE.md"
specifications = "changes"
plans = "changes"
decisions = "docs/decisions"
delivery_state = ".reposeal/delivery"
""",
            "reposeal.template_version must be semantic",
        ),
        (
            "reposeal.toml",
            """schema_version = 2
[reposeal]
protocol = 2
template_version = "0.2.0"
[profiles]
enabled = ["python-default@1", "python-default@1"]
[repository]
architecture = "docs/ARCHITECTURE.md"
specifications = "changes"
plans = "changes"
decisions = "docs/decisions"
delivery_state = ".reposeal/delivery"
""",
            "profiles.enabled must contain unique identities",
        ),
    ],
)
def test_invalid_manifest_is_rejected(tmp_path: Path, name: str, text: str, message: str) -> None:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)
