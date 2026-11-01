"""Observe the executed engine content, independently of an application environment."""

import json
import sys
from importlib.metadata import version
from pathlib import Path

from signetum import __version__
from signetum.skill_identity import labeled_content_digest


def implementation_digest() -> str:
    root = Path(__file__).parent
    entries = []
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix in {".py", ".json", ".toml"}
            and "__pycache__" not in path.parts
        ):
            entries.append((path.relative_to(root).as_posix(), path.read_bytes()))
    return labeled_content_digest(entries)


def identity() -> dict[str, object]:
    return {
        "version": __version__,
        "implementation": implementation_digest(),
        "python": sys.version,
        "dependencies": {name: version(name) for name in ("pydantic", "PyYAML", "typer")},
    }


if __name__ == "__main__":
    print(json.dumps(identity(), sort_keys=True))
