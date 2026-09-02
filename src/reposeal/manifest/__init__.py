"""Typed RepoSeal v2 repository configuration boundary."""

from pathlib import Path
from re import fullmatch
from tomllib import TOMLDecodeError, loads
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)


class ManifestError(ValueError):
    """A repository configuration violates the supported public contract."""


class RepoSealIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol: int = Field(strict=True, ge=2)
    template_version: str
    evidence_protocol: str = "reposeal.validation-evidence@3"
    evidence_schema_digest: str = (
        "sha256:0c3d852d5f2a21856cfde4f31088f4a8527f98cf63d53614d073966187e5be12"
    )

    @field_validator("template_version")
    @classmethod
    def validate_template_version(cls, value: str) -> str:
        if fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", value) is None:
            raise ValueError("reposeal.template_version must be semantic")
        return value

    @field_validator("evidence_protocol")
    @classmethod
    def validate_evidence_protocol(cls, value: str) -> str:
        if value != "reposeal.validation-evidence@3":
            raise ValueError(f"unsupported evidence protocol: {value}")
        return value

    @field_validator("evidence_schema_digest")
    @classmethod
    def validate_evidence_schema_digest(cls, value: str) -> str:
        if fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
            raise ValueError("evidence schema digest must be sha256")
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


class ValidationTool(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    identity_command: tuple[str, ...]


class ValidationShard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    command: tuple[str, ...]
    requires: tuple[str, ...] = ()
    evidence: Literal["tree", "world"] = "tree"
    findings_command: tuple[str, ...] = ()
    timeout_seconds: int = Field(default=1800, gt=0)

    @field_validator("findings_command")
    @classmethod
    def validate_findings_command(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        if value and info.data.get("evidence") != "world":
            raise ValueError("only a world shard declares a findings command")
        return value


class ValidationGate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    shards: tuple[str, ...]


class ValidationCommands(BaseModel):
    """Strict named validation graph and member completeness boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tools: tuple[ValidationTool, ...] = ()
    shards: tuple[ValidationShard, ...]
    gates: tuple[ValidationGate, ...]
    member_required: tuple[str, ...] = ()

    @field_validator("shards")
    @classmethod
    def validate_unique_shards(
        cls, value: tuple[ValidationShard, ...]
    ) -> tuple[ValidationShard, ...]:
        if not value or len(value) != len({item.name for item in value}):
            raise ValueError("validation.shards must contain unique named shards")
        return value

    @field_validator("gates")
    @classmethod
    def validate_unique_gates(cls, value: tuple[ValidationGate, ...]) -> tuple[ValidationGate, ...]:
        names = {item.name for item in value}
        if len(value) != len(names) or "member" not in names or "final" not in names:
            raise ValueError("validation.gates must contain unique member and final gates")
        return value

    @model_validator(mode="after")
    def validate_member_closure_is_tree_determined(self) -> "ValidationCommands":
        """Keep member closure independent of state the member does not own."""

        world = {item.name for item in self.shards if item.evidence == "world"}
        declared = {item.name for item in self.shards}
        member = next((item.shards for item in self.gates if item.name == "member"), ())
        for origin, names in (("gates.member", member), ("member_required", self.member_required)):
            unknown = sorted(set(names) - declared)
            if unknown:
                raise ValueError(
                    f"validation.{origin} names undeclared shards: {', '.join(unknown)}"
                )
            blocking = sorted(set(names) & world)
            if blocking:
                raise ValueError(
                    f"validation.{origin} cannot depend on world state: {', '.join(blocking)}"
                )
        return self


class RepositoryManifest(BaseModel):
    """Supported language-neutral version-two repository configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(strict=True)
    reposeal: RepoSealIdentity
    profiles: ProfileSelection = Field(default_factory=ProfileSelection)
    repository: RepositoryBindings
    impact: ImpactConfiguration = Field(default_factory=ImpactConfiguration)
    validation: ValidationCommands


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
    "ValidationCommands",
    "ValidationGate",
    "ValidationShard",
    "ValidationTool",
    "load_manifest",
]
