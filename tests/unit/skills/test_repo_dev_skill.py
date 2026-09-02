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
    resources = {path.relative_to(SKILL).as_posix() for path in (SKILL / "references").glob("*.md")}

    assert links == resources
    for relative in links:
        assert (SKILL / relative).is_file()


_PATH_LIKE = re.compile(r"[A-Za-z0-9_.*-]+(?:/[A-Za-z0-9_.*-]+)*\.(?:toml|ya?ml|json|md|py)")


def test_generic_skill_cites_only_paths_it_ships() -> None:
    """The router names no repository's authorities, not merely none we listed.

    A forbidden-token list only catches the downstream names somebody
    remembered. Every path this skill cites resolving to a file it ships is the
    same contract stated so it holds for the ones nobody enumerated.
    """
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(SKILL.rglob("*.md")))

    cited = set(_PATH_LIKE.findall(text))

    assert cited
    assert {path for path in cited if not (SKILL / path).is_file()} == set()


def test_skill_declares_an_immutable_release_version() -> None:
    frontmatter = ENTRYPOINT.read_text(encoding="utf-8").split("---", 2)[1]

    assert re.search(r'^  version: "[0-9]+\.[0-9]+\.[0-9]+"$', frontmatter, re.MULTILINE)
