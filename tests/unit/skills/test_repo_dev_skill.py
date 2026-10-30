"""Structural contracts for the versioned Signetum Skill."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[3]
SKILL = ROOT / "skills" / "signetum"
ENTRYPOINT = SKILL / "SKILL.md"


def _entrypoint_links() -> set[str]:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    return set(re.findall(r"\]\((references/[^)]+\.md)\)", text))


def test_entrypoint_links_resolve_to_packaged_references() -> None:
    links = _entrypoint_links()
    resources = {path.relative_to(SKILL).as_posix() for path in (SKILL / "references").glob("*.md")}

    assert links and links <= resources
    for relative in links:
        assert (SKILL / relative).is_file()


def test_skill_declares_an_immutable_release_version() -> None:
    frontmatter = yaml.safe_load(ENTRYPOINT.read_text(encoding="utf-8").split("---", 2)[1])
    assert frontmatter["name"] == SKILL.name
    version = frontmatter["metadata"]["version"]
    assert isinstance(version, str)
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
