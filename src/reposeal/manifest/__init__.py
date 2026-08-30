"""Typed RepoSeal v2 repository configuration boundary."""

from pathlib import Path
from re import fullmatch
from tomllib import TOMLDecodeError, loads

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator


class ManifestError(ValueError):
    """A repository configuration violates the supported public contract."""


class RepoSealIdentity(BaseModel):
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
    """Ordered profile composition with explicit named replacements."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: tuple[str, ...] = ()
    replacements: dict[str, str] = Field(default_factory=dict)

    @field_validator("enabled")
    @classmethod
    def validate_enabled(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("profiles.enabled must contain unique identities")
        for identity in value:
            _validate_profile_identity(identity)
        return value

    @field_validator("replacements")
    @classmethod
    def validate_replacements(cls, value: dict[str, str]) -> dict[str, str]:
        for target, replacement in value.items():
            _validate_profile_identity(target)
            _validate_profile_identity(replacement)
            if target == replacement:
                raise ValueError("a profile cannot replace itself")
        return value


class RepositoryBindings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    architecture: str
    specifications: str
    plans: str
    decisions: str
    delivery_state: str
    lockfiles: tuple[str, ...] = ()

    @field_validator("*")
    @classmethod
    def validate_relative_paths(cls, value: object, info: object) -> object:
        values = value if isinstance(value, tuple) else (value,)
        for item in values:
            if not isinstance(item, str):
                continue
            path = Path(item)
            if path.is_absolute() or ".." in path.parts:
                field_name = getattr(info, "field_name", "path")
                raise ValueError(f"repository.{field_name} must be repository-relative")
        return value


class ImpactRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    paths: tuple[str, ...] = Field(min_length=1)
    profiles: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    shards: tuple[str, ...] = ()
    requires_final: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if fullmatch(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*", value) is None:
            raise ValueError(f"impact rule name must be namespaced: {value}")
        return value

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for raw in value:
            path = Path(raw)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"impact path must be repository-relative: {raw}")
        return value


class ImpactConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: tuple[ImpactRule, ...] = ()

    @field_validator("rules")
    @classmethod
    def validate_unique_names(cls, value: tuple[ImpactRule, ...]) -> tuple[ImpactRule, ...]:
        names = tuple(rule.name for rule in value)
        if len(names) != len(set(names)):
            raise ValueError("impact.rules names must be unique")
        return value


class RepositoryManifest(BaseModel):
    """Supported language-neutral version-two repository configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(strict=True)
    reposeal: RepoSealIdentity
    profiles: ProfileSelection = Field(default_factory=ProfileSelection)
    repository: RepositoryBindings
    impact: ImpactConfiguration = Field(default_factory=ImpactConfiguration)


_MAPPING = TypeAdapter(dict[str, object])


def _validate_profile_identity(value: str) -> None:
    if fullmatch(r"[a-z][a-z0-9-]*@[1-9][0-9]*", value) is None:
        raise ValueError(f"profile identity must be immutable: {value}")


def load_manifest(path: str | Path) -> RepositoryManifest:
    """Load the sole TOML configuration format without fallback behavior."""

    source = Path(path)
    if source.name != "reposeal.toml":
        raise ManifestError("active configuration must be named reposeal.toml")
    try:
        data = _MAPPING.validate_python(loads(source.read_text(encoding="utf-8")))
    except (OSError, TOMLDecodeError, ValidationError) as error:
        raise ManifestError(str(error)) from error
    schema_version = data.get("schema_version")
    if schema_version != 2:
        raise ManifestError(f"unsupported manifest schema: {schema_version}")
    try:
        return RepositoryManifest.model_validate(data)
    except ValidationError as error:
        first = error.errors()[0]
        message = str(first["msg"]).removeprefix("Value error, ")
        raise ManifestError(message) from error


__all__ = [
    "ImpactConfiguration",
    "ImpactRule",
    "ManifestError",
    "ProfileSelection",
    "RepoSealIdentity",
    "RepositoryBindings",
    "RepositoryManifest",
    "load_manifest",
]
