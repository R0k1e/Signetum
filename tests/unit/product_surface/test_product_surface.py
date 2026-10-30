from pathlib import Path

import pytest
import yaml

from signetum.product_surface import validate_product_surface
from signetum.traceability.boundary import RepositoryInventory


def _inventory(*paths: str) -> RepositoryInventory:
    return RepositoryInventory(paths=frozenset(paths))


def test_complete_public_surface_passes_observable_contract(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    guide = tmp_path / "docs" / "guide.md"
    guide.parent.mkdir()
    readme.write_text("Read the [guide](docs/guide.md).\n", encoding="utf-8")
    guide.write_text("# Guide\n", encoding="utf-8")

    report = validate_product_surface(
        tmp_path,
        _inventory("README.md", "docs/guide.md"),
        required_paths=("README.md", "docs/guide.md"),
        required_content={},
    )

    assert report.valid is True
    assert report.issues == ()


def test_missing_required_asset_reports_the_exact_path(tmp_path: Path) -> None:
    report = validate_product_surface(
        tmp_path,
        _inventory("README.md"),
        required_paths=("README.md", "QUICKSTART.md"),
        required_content={},
    )

    assert report.valid is False
    assert report.issues[0].code == "missing-required-asset"
    assert report.issues[0].target == "QUICKSTART.md"


def test_explicit_content_policy_reports_its_unmet_declared_requirements(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Unrelated fixture content\n", encoding="utf-8")

    report = validate_product_surface(
        tmp_path,
        _inventory("README.md"),
        required_paths=("README.md",),
        required_content={"README.md": ("required-token-a", "required-token-b")},
    )

    assert report.valid is False
    assert [issue.code for issue in report.issues] == [
        "missing-required-content",
        "missing-required-content",
    ]
    assert {issue.target for issue in report.issues} == {
        "required-token-a",
        "required-token-b",
    }


def test_missing_local_markdown_target_reports_source_and_target(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Read [missing](docs/missing.md).\n", encoding="utf-8")

    report = validate_product_surface(
        tmp_path,
        _inventory("README.md"),
        required_paths=("README.md",),
        required_content={},
    )

    assert report.valid is False
    assert report.issues[0].code == "broken-markdown-link"
    assert report.issues[0].source == "README.md"
    assert report.issues[0].target == "docs/missing.md"


def test_external_links_and_anchors_are_not_local_file_contracts(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "[section](#section) [web](https://example.com) [mail](mailto:a@example.com)\n",
        encoding="utf-8",
    )

    report = validate_product_surface(
        tmp_path,
        _inventory("README.md"),
        required_paths=("README.md",),
        required_content={},
    )

    assert report.valid is True


def test_relative_parent_root_and_encoded_links_resolve_against_inventory(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    guide = docs / "guide.md"
    guide.write_text(
        "[readme](../README.md) [root](/LICENSE) [space](<other%20guide.md>)\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Product\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("license\n", encoding="utf-8")
    (docs / "other guide.md").write_text("# Other\n", encoding="utf-8")

    report = validate_product_surface(
        tmp_path,
        _inventory("docs/guide.md", "README.md", "LICENSE", "docs/other guide.md"),
        required_paths=("docs/guide.md",),
        required_content={},
    )

    assert report.valid is True


def test_link_that_escapes_repository_is_not_treated_as_a_local_asset(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("[outside](../outside.md)\n", encoding="utf-8")

    report = validate_product_surface(
        tmp_path,
        _inventory("README.md"),
        required_paths=("README.md",),
        required_content={},
    )

    assert report.valid is True


@pytest.mark.parametrize("damage", [None, "permission", "permission-shape", "checkout", "action"])
def test_structured_workflow_policy_checks_safety_without_pinning_commands(tmp_path, damage):
    action = "actions/checkout@" + "a" * 40
    workflow = {
        "permissions": {"contents": "read"},
        "jobs": {
            "test": {
                "steps": [
                    {"uses": action, "with": {"ref": "${{ github.sha }}"}},
                    {"run": "an-arbitrary-valid-diagnostic-entrypoint"},
                ]
            }
        },
    }
    if damage == "permission":
        workflow["permissions"] = {"contents": "write"}
    elif damage == "permission-shape":
        workflow["permissions"] = {"contents": ["read"]}
    elif damage == "checkout":
        workflow["jobs"]["test"]["steps"][0]["with"]["ref"] = "main"
    elif damage == "action":
        workflow["jobs"]["test"]["steps"][0]["uses"] = "actions/checkout@main"
    path = tmp_path / ".github/workflows/ci.yml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(workflow))
    result = validate_product_surface(
        tmp_path, _inventory(".github/workflows/ci.yml"), required_paths=(), required_content={}
    )
    assert result.valid is (damage is None)
    if damage:
        assert result.issues[0].code == "invalid-workflow-policy"

    composite = tmp_path / ".github/actions/check/action.yml"
    composite.parent.mkdir(parents=True)
    composite.write_text(
        yaml.safe_dump({"runs": {"using": "composite", "steps": workflow["jobs"]["test"]["steps"]}})
    )
    result = validate_product_surface(
        tmp_path,
        _inventory(".github/actions/check/action.yml"),
        required_paths=(),
        required_content={},
    )
    assert result.valid is (damage not in {"checkout", "action"})

    delegated = {
        "permissions": {"contents": "read"},
        "jobs": {
            "test": {
                "uses": "owner/repo/.github/workflows/check.yml@"
                + ("main" if damage == "action" else "a" * 40)
            }
        },
    }
    path.write_text(yaml.safe_dump(delegated))
    result = validate_product_surface(
        tmp_path, _inventory(".github/workflows/ci.yml"), required_paths=(), required_content={}
    )
    assert result.valid is (damage != "action")
