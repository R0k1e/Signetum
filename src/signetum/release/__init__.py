"""Immutable release-set metadata and exact-source preflight."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from yaml import YAMLError, safe_load

from signetum import __version__
from signetum.git import GitError, GitInfrastructureError, git_output
from signetum.policy import delivery_policy


class ReleaseError(ValueError):
    """A release candidate does not bind one validated source identity."""


class ReleaseComponent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Literal["package", "schemas", "signetum-skill"]
    version: str = Field(min_length=1)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ReleaseMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[2] = 2
    source: str = Field(min_length=1)
    components: tuple[ReleaseComponent, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique_components(self) -> Self:
        if len({component.name for component in self.components}) != 3:
            raise ValueError("release requires each component identity exactly once")
        return self


def digest_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _skill_identity(repository: Path) -> tuple[str, str]:
    root = repository / "skills" / "signetum"
    try:
        frontmatter = safe_load((root / "SKILL.md").read_text().split("---", 2)[1])
        version = frontmatter["metadata"]["version"]
        if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
            raise ValueError("Skill version must be an explicit semantic version")
    except (IndexError, KeyError, TypeError, ValueError, YAMLError) as error:
        raise ReleaseError(f"invalid Skill identity: {error}") from error
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ReleaseError("Skill release cannot contain symlinks")
        if path.is_file():
            content = path.read_bytes()
            digest.update(json.dumps([path.relative_to(root).as_posix(), len(content)]).encode())
            digest.update(content)
    return version, "sha256:" + digest.hexdigest()


def build_metadata(repository: Path, source: str) -> ReleaseMetadata:
    schema_path = repository / "schemas" / "release-metadata.schema.json"
    try:
        package = tomllib.loads((repository / "pyproject.toml").read_text())["project"]["version"]
        schema_version = json.loads(schema_path.read_text())["properties"]["schema_version"][
            "const"
        ]
        if type(schema_version) is not int or schema_version != 2:
            raise ValueError("release metadata requires schema version two")
    except (KeyError, TypeError, ValueError) as error:
        raise ReleaseError(f"invalid release component identity: {error}") from error
    if package != __version__:
        raise ReleaseError("installed engine version differs from release source")
    skill_version, skill_digest = _skill_identity(repository)
    if skill_version != package:
        raise ReleaseError("Skill and package must share the product version")
    return ReleaseMetadata(
        source=source,
        components=(
            ReleaseComponent(
                name="schemas", version=str(schema_version), digest=digest_path(schema_path)
            ),
            ReleaseComponent(name="signetum-skill", version=skill_version, digest=skill_digest),
            ReleaseComponent(
                name="package", version=package, digest=digest_path(repository / "pyproject.toml")
            ),
        ),
    )


def preflight(repository: Path, source: str, *, tag: str | None = None) -> ReleaseMetadata:
    """Check source eligibility; validation and publication authorization stay separate."""

    def observe(*arguments: str) -> str:
        try:
            return git_output(repository, *arguments)
        except GitInfrastructureError:
            raise
        except GitError as error:
            raise ReleaseError(f"release source check {arguments[0]} failed: {error}") from error

    if observe("rev-parse", "HEAD") != source:
        raise ReleaseError("release source differs from HEAD")
    if observe("status", "--porcelain"):
        raise ReleaseError("release source worktree is dirty")
    branch = delivery_policy(repository).branch
    observe("merge-base", "--is-ancestor", source, f"refs/remotes/origin/{branch}")
    metadata = build_metadata(repository, source)
    if tag is not None:
        if tag != "v" + __version__:
            raise ReleaseError("release tag differs from engine version")
        if observe("rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}") != source:
            raise ReleaseError("release tag differs from source")
    return metadata


__all__ = ["ReleaseComponent", "ReleaseError", "ReleaseMetadata", "build_metadata", "preflight"]
