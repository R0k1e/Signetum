"""Typed repository specialization manifest boundary."""

from pathlib import Path
from re import fullmatch

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator


class ManifestError(ValueError):
    """A repository manifest violates a supported public contract."""


class RepoSealIdentity(BaseModel):
    """Pinned identity of one compatible RepoSeal release."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    digest: str

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", value) is None:
            raise ValueError("reposeal.version must be an immutable semantic version")
        return value

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
            raise ValueError("reposeal.digest must be a sha256 identity")
        return value


class ProfileSelection(BaseModel):
    """One explicitly selected, versioned policy profile."""

    model_config = ConfigDict(frozen=True)

    identity: str


class RepositoryBindings(BaseModel):
    """Paths owned by the consuming repository."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    architecture: str
    specifications: str
    plans: str
    decisions: str
    validation: str
    delivery_state: str

    @field_validator("*")
    @classmethod
    def validate_relative_path(cls, value: str, info: object) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            field_name = getattr(info, "field_name", "path")
            raise ValueError(f"repository.{field_name} must be repository-relative")
        return value


class RepositoryManifest(BaseModel):
    """Supported version-one specialization manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(strict=True)
    reposeal: RepoSealIdentity
    profiles: tuple[str, ...]
    repository: RepositoryBindings

    @field_validator("profiles")
    @classmethod
    def validate_profiles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("profiles must contain unique identities")
        for identity in value:
            if fullmatch(r"[a-z][a-z0-9-]*@[1-9][0-9]*", identity) is None:
                raise ValueError(f"profile identity must be immutable: {identity}")
        return value


_MAPPING = TypeAdapter(dict[str, object])


def load_manifest(path: str | Path) -> RepositoryManifest:
    """Load and validate a manifest without schema fallback behavior."""

    source = Path(path)
    try:
        data = _MAPPING.validate_python(yaml.safe_load(source.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ManifestError(str(error)) from error

    schema_version = data.get("schema_version")
    if schema_version != 1:
        raise ManifestError(f"unsupported manifest schema: {schema_version}")

    try:
        return RepositoryManifest.model_validate(data)
    except ValidationError as error:
        first = error.errors()[0]
        message = str(first["msg"]).removeprefix("Value error, ")
        raise ManifestError(message) from error


__all__ = [
    "ManifestError",
    "ProfileSelection",
    "RepoSealIdentity",
    "RepositoryBindings",
    "RepositoryManifest",
    "load_manifest",
]
