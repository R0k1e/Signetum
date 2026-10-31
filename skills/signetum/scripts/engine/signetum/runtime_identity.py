"""Observe the executed engine content, independently of an application environment."""

import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path

from signetum import __version__


def implementation_digest() -> str:
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix in {".py", ".json", ".toml"}
            and "__pycache__" not in path.parts
        ):
            relative = path.relative_to(root).as_posix()
            content = path.read_bytes()
            digest.update(json.dumps([relative, len(content)]).encode())
            digest.update(content)
    return "sha256:" + digest.hexdigest()


def identity() -> dict[str, object]:
    return {
        "version": __version__,
        "implementation": implementation_digest(),
        "python": sys.version,
        "dependencies": {name: version(name) for name in ("pydantic", "PyYAML", "typer")},
    }


if __name__ == "__main__":
    print(json.dumps(identity(), sort_keys=True))
