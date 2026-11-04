"""Immutable release-set metadata and exact-source preflight."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Literal, Self
from zipfile import ZIP_DEFLATED, ZipFile

from pydantic import BaseModel, ConfigDict, Field, model_validator
from signetum import __version__
from signetum.git import GitError, GitInfrastructureError, git_output
from signetum.policy import delivery_policy
from signetum.skill_identity import skill_files, skill_identity
from yaml import YAMLError


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


PLUGIN = Path("plugins/signetum")
SKILL = PLUGIN / "skills/signetum"
ENGINE = SKILL / "scripts/engine"
MARKETPLACE = Path(".claude-plugin/marketplace.json")


def digest_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _skill_identity(root: Path) -> tuple[str, str]:
    try:
        return skill_identity(root)
    except (IndexError, KeyError, TypeError, ValueError, YAMLError) as error:
        raise ReleaseError(f"invalid Skill identity: {error}") from error


def build_skill_archive(repository: Path, destination: Path) -> Path:
    """Build the complete standard Skill without machine-local generated material."""
    version, _ = _skill_identity(repository / SKILL)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f"signetum-skill-{version}.zip"
    root = repository / SKILL
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in skill_files(root):
            archive.write(path, "signetum/" + path.relative_to(root).as_posix())
    return output


def build_metadata(repository: Path, source: str) -> ReleaseMetadata:
    schema_path = repository / ENGINE / "signetum/resources/schemas/release-metadata-v2.schema.json"
    try:
        package = tomllib.loads((repository / ENGINE / "pyproject.toml").read_text())["project"][
            "version"
        ]
        plugin = json.loads((repository / PLUGIN / ".claude-plugin/plugin.json").read_text())
        schema_version = json.loads(schema_path.read_text())["properties"]["schema_version"][
            "const"
        ]
        if type(schema_version) is not int or schema_version != 2:
            raise ValueError("release metadata requires schema version two")
    except (KeyError, TypeError, ValueError) as error:
        raise ReleaseError(f"invalid release component identity: {error}") from error
    if package != __version__:
        raise ReleaseError("installed engine version differs from release source")
    skill_version, skill_digest = _skill_identity(repository / SKILL)
    if skill_version != package:
        raise ReleaseError("Skill and package must share the product version")
    if plugin.get("name") != "signetum" or plugin.get("version") != package:
        raise ReleaseError("plugin manifest and package must share the product version")
    return ReleaseMetadata(
        source=source,
        components=(
            ReleaseComponent(
                name="schemas", version=str(schema_version), digest=digest_path(schema_path)
            ),
            ReleaseComponent(name="signetum-skill", version=skill_version, digest=skill_digest),
            ReleaseComponent(
                name="package",
                version=package,
                digest=digest_path(repository / ENGINE / "pyproject.toml"),
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


def marketplace_pin(version: str, source: str) -> dict[str, object]:
    """The marketplace document that makes one released commit the installable plugin."""

    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ReleaseError("marketplace pin requires a semantic product version")
    if re.fullmatch(r"[0-9a-f]{40}", source) is None:
        raise ReleaseError("marketplace pin requires an exact 40-hex release commit")
    return {
        "name": "signetum",
        "owner": {"name": "R0k1e"},
        "plugins": [
            {
                "name": "signetum",
                "version": version,
                "description": "Reliable Agent development and delivery with a command guard.",
                "source": {
                    "source": "git-subdir",
                    "url": "https://github.com/R0k1e/Signetum.git",
                    "path": PLUGIN.as_posix(),
                    "ref": "v" + version,
                    "sha": source,
                },
            }
        ],
    }


def write_marketplace_pin(repository: Path, metadata: ReleaseMetadata) -> Path:
    """Write the release pin for a preflighted source; committing it publishes the plugin."""

    version = next(c.version for c in metadata.components if c.name == "package")
    path = repository / MARKETPLACE
    path.parent.mkdir(parents=True, exist_ok=True)
    document = marketplace_pin(version, metadata.source)
    path.write_text(json.dumps(document, indent=2) + "\n")
    return path


__all__ = [
    "ReleaseComponent",
    "ReleaseError",
    "ReleaseMetadata",
    "build_metadata",
    "marketplace_pin",
    "preflight",
    "write_marketplace_pin",
]
