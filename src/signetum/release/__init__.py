"""Immutable release-set metadata and exact-source preflight."""

from __future__ import annotations

import hashlib
import json
import subprocess  # nosec B404
from pathlib import Path
from shutil import which

from pydantic import BaseModel, ConfigDict, Field

from signetum import __version__


class ReleaseError(ValueError):
    """A release candidate does not bind one validated source identity."""


class ReleaseComponent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ReleaseMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    source: str
    components: tuple[ReleaseComponent, ...]


def digest_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_metadata(repository: Path, source: str) -> ReleaseMetadata:
    components = (
        ReleaseComponent(
            name="schemas",
            version=__version__,
            digest=digest_path(repository / "schemas" / "release-metadata.schema.json"),
        ),
        ReleaseComponent(
            name="repo-dev",
            version=__version__,
            digest=digest_path(repository / "skills" / "repo-dev" / "SKILL.md"),
        ),
        ReleaseComponent(
            name="package",
            version=__version__,
            digest=digest_path(repository / "pyproject.toml"),
        ),
    )
    return ReleaseMetadata(source=source, components=components)


def preflight(repository: Path, source: str) -> ReleaseMetadata:
    git = which("git")
    if git is None:
        raise ReleaseError("git executable is unavailable")
    completed = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    if completed.stdout.strip() != source:
        raise ReleaseError("release source differs from HEAD")
    dirty = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "status", "--porcelain"),
        check=True,
        capture_output=True,
        text=True,
    )
    if dirty.stdout:
        raise ReleaseError("release source worktree is dirty")
    common = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "rev-parse", "--git-common-dir"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = repository / common_path
    receipts = sorted((common_path.resolve() / "signetum" / "validation").glob("final-*.json"))
    if not receipts:
        raise ReleaseError("final receipt is absent")
    if not any(
        json.loads(path.read_text(encoding="utf-8")).get("source") == source for path in receipts
    ):
        raise ReleaseError("final receipt does not bind release source")
    return build_metadata(repository, source)


__all__ = ["ReleaseComponent", "ReleaseError", "ReleaseMetadata", "build_metadata", "preflight"]
