"""Structural contracts for the versioned generic repo-dev skill."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[3]
SKILL = ROOT / "skills" / "repo-dev"
ENTRYPOINT = SKILL / "SKILL.md"


def _entrypoint_links() -> set[str]:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    return set(re.findall(r"\]\((references/[^)]+\.md)\)", text))


def test_entrypoint_routes_every_focused_reference() -> None:
    links = _entrypoint_links()
    resources = {
        path.relative_to(SKILL).as_posix()
        for path in (SKILL / "references").glob("*.md")
    }

    assert links == resources
    for relative in links:
        assert (SKILL / relative).is_file()


def test_generic_skill_contains_no_downstream_authorities() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SKILL.rglob("*.md"))
    )
    forbidden = (
        "PyLM",
        ".agents/repo-dev/repo.yaml",
        "origin/product",
        "changes/",
        "specs/",
        "plans/",
        "just changed",
        "just ready",
    )

    assert not [token for token in forbidden if token in text]


def test_skill_declares_an_immutable_release_version() -> None:
    frontmatter = ENTRYPOINT.read_text(encoding="utf-8").split("---", 2)[1]

    assert re.search(
        r'^  version: "[0-9]+\.[0-9]+\.[0-9]+"$', frontmatter, re.MULTILINE
    )
