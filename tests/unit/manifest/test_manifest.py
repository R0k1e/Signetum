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
    assert manifest.validation.member[0] == ("git", "diff", "--check")
    assert manifest.validation.final[-1] == ("mise", "run", "python:secrets")


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


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ('enabled = ["not-versioned"]', "profile identity must be immutable"),
        (
            'enabled = ["python-default@1"]\n'
            '[profiles.replacements]\n"python-default@1" = "python-default@1"',
            "a profile cannot replace itself",
        ),
    ],
)
def test_profile_composition_errors_fail_closed(tmp_path: Path, extra: str, message: str) -> None:
    path = tmp_path / "reposeal.toml"
    path.write_text(
        f"""schema_version = 2
[reposeal]
protocol = 2
template_version = "0.2.0"
[profiles]
{extra}
[repository]
architecture = "docs/ARCHITECTURE.md"
specifications = "changes"
plans = "changes"
decisions = "docs/decisions"
delivery_state = ".reposeal/delivery"
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ('name = "Invalid"\npaths = ["src/**"]', "impact rule name must be namespaced"),
        ('name = "valid.rule"\npaths = ["../outside"]', "impact path must be"),
        (
            'name = "same.rule"\npaths = ["src/**"]\n'
            '[[impact.rules]]\nname = "same.rule"\npaths = ["tests/**"]',
            "impact.rules names must be unique",
        ),
    ],
)
def test_impact_contract_rejects_ambiguous_or_escaping_rules(
    tmp_path: Path, rule: str, message: str
) -> None:
    path = tmp_path / "reposeal.toml"
    path.write_text(
        f"""schema_version = 2
[reposeal]
protocol = 2
template_version = "0.2.0"
[repository]
architecture = "docs/ARCHITECTURE.md"
specifications = "changes"
plans = "changes"
decisions = "docs/decisions"
delivery_state = ".reposeal/delivery"
[[impact.rules]]
{rule}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)


def test_missing_configuration_is_an_invocation_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "reposeal.toml")


@pytest.mark.parametrize(
    ("validation", "message"),
    [
        ('member = []\nfinal = [["git", "diff", "--check"]]', "must contain at least one"),
        (
            'member = ["git diff --check"]\nfinal = [["git", "diff", "--check"]]',
            "valid argv arrays",
        ),
        (
            'member = [["git", "diff", "--check"]]\nfinal = [["git", ""]]',
            "non-empty strings",
        ),
    ],
)
def test_validation_commands_are_strict_shell_free_argv(
    tmp_path: Path, validation: str, message: str
) -> None:
    path = tmp_path / "reposeal.toml"
    path.write_text(
        f"""schema_version = 2
[reposeal]
protocol = 2
template_version = "0.2.0"
[repository]
architecture = "docs/ARCHITECTURE.md"
specifications = "changes"
plans = "changes"
decisions = "docs/decisions"
delivery_state = ".reposeal/delivery"
[validation]
{validation}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)
