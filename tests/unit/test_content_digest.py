"""Skill packaging and engine implementation keep separate identities."""

from pathlib import Path

from signetum.runtime_identity import implementation_digest
from signetum.skill_identity import content_digest, labeled_content_digest


def test_one_hasher_keeps_skill_packaging_outside_engine_identity(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_bytes(b"guide")
    (skill / "scripts" / "launch.py").write_bytes(b"print(1)\n")
    packaged = content_digest(skill)
    assert packaged == labeled_content_digest(
        [("SKILL.md", b"guide"), ("scripts/launch.py", b"print(1)\n")]
    )
    assert packaged != labeled_content_digest([("scripts/launch.py", b"print(1)\n")])

    root = Path(implementation_digest.__code__.co_filename).parent
    entries = []
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix in {".py", ".json", ".toml"}
            and "__pycache__" not in path.parts
        ):
            entries.append((path.relative_to(root).as_posix(), path.read_bytes()))
    assert implementation_digest() == labeled_content_digest(entries)
    assert all(name != "SKILL.md" for name, _content in entries)
