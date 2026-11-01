"""Identity of the complete distributed Skill, separate from execution evidence."""

import hashlib
import json
import re
from pathlib import Path


def skill_files(root: Path) -> tuple[Path, ...]:
    paths = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in {".runtime", ".venv", "__pycache__", "dist"} for part in relative.parts):
            continue
        if path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError("Skill cannot contain symlinks")
        if path.is_file():
            paths.append(path)
    return tuple(paths)


def content_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in skill_files(root):
        content = path.read_bytes()
        digest.update(json.dumps([path.relative_to(root).as_posix(), len(content)]).encode())
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def skill_identity(root: Path) -> tuple[str, str]:
    from yaml import safe_load  # noqa: PLC0415 -- prepared runtime version parsing

    frontmatter = safe_load((root / "SKILL.md").read_text().split("---", 2)[1])
    version = frontmatter["metadata"]["version"]

    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError("Skill version must be an explicit semantic version")
    return version, content_digest(root)


if __name__ == "__main__":
    import sys

    version, content = skill_identity(Path(sys.argv[1]))
    print(json.dumps({"version": version, "content_digest": content}, sort_keys=True))
