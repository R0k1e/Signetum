"""Identify the installed Python validation implementation, including editable code."""

import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path


def identity() -> str:
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for source in sorted(package.rglob("*.py")):
        digest.update(source.relative_to(package).as_posix().encode() + b"\0")
        digest.update(source.read_bytes() + b"\0")
    return json.dumps(
        {
            "python": sys.version,
            "packages": {
                name: version(name) for name in ("signetum", "pydantic", "pyyaml", "typer")
            },
            "implementation": "sha256:" + digest.hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


if __name__ == "__main__":
    print(identity())
