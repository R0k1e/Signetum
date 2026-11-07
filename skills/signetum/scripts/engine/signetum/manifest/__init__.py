"""Portable typed Signetum repository configuration boundary."""

from dataclasses import dataclass, field, fields
from pathlib import Path
from re import fullmatch
from tomllib import loads

from signetum.profiles.catalog import validate_selection
from signetum.resources.schemas import evidence_schema_digest as published_evidence_schema_digest
from signetum.selection_contracts import SelectionProvider, repository_file
from signetum.serialization import UnknownFieldsError, dataclass_from_mapping
from signetum.validation import SCHEDULE_FILE, ValidationShard
from signetum.validation import GateDeclaration as ValidationGate
from signetum.validation import ToolDeclaration as ValidationTool

SCHEMA_VERSION = 5


class ManifestError(ValueError):
    """A repository configuration violates the supported public contract."""


class UnsupportedManifestError(ManifestError):
    """The manifest uses a schema or fields this engine does not know, as a newer one may."""


@dataclass(frozen=True, kw_only=True)
class SignetumIdentity:
    protocol: int
    evidence_protocol: str = "reposeal.validation-evidence@3"
    evidence_schema_digest: str = field(default_factory=published_evidence_schema_digest)

    def __post_init__(self) -> None:
        if self.protocol != 2:
            raise ManifestError("unsupported signetum protocol; supported version is 2")
        if self.evidence_protocol != "reposeal.validation-evidence@3":
            raise ManifestError(f"unsupported evidence protocol: {self.evidence_protocol}")
        if self.evidence_schema_digest != published_evidence_schema_digest():
            raise ManifestError("evidence schema digest does not match the published schema")


@dataclass(frozen=True, kw_only=True)
class ProfileSelection:
    enabled: tuple[str, ...] = ()
    replacements: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_selection(self.enabled, self.replacements)


@dataclass(frozen=True, kw_only=True)
class RepositoryBindings:
    architecture: str = ""
    changes: str
    decisions: str
    lockfiles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        repository_file(self.changes)
        if self.changes == "." or any(character in self.changes for character in "*?[]"):
            raise ManifestError("repository.changes must name an exact directory")
        for item in fields(self):
            value = getattr(self, item.name)
            for raw in value if isinstance(value, tuple) else (value,):
                path = Path(raw)
                if path.is_absolute() or ".." in path.parts:
                    raise ManifestError(f"repository.{item.name} must be repository-relative")


@dataclass(frozen=True, kw_only=True)
class ImpactRule:
    name: str
    paths: tuple[str, ...]
    profiles: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    shards: tuple[str, ...] = ()
    requires_final: bool = False

    def __post_init__(self) -> None:
        if fullmatch(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*", self.name) is None:
            raise ManifestError(f"impact rule name must be namespaced: {self.name}")
        if not self.paths:
            raise ManifestError("impact paths must be non-empty")
        for raw in self.paths:
            path = Path(raw)
            if path.is_absolute() or ".." in path.parts:
                raise ManifestError(f"impact path must be repository-relative: {raw}")


@dataclass(frozen=True, kw_only=True)
class ImpactConfiguration:
    rules: tuple[ImpactRule, ...] = ()
    provider: SelectionProvider | None = None

    def __post_init__(self) -> None:
        if len(self.rules) != len({rule.name for rule in self.rules}):
            raise ManifestError("impact.rules names must be unique")


@dataclass(frozen=True, kw_only=True)
class ValidationCommands:
    tools: tuple[ValidationTool, ...] = ()
    shards: tuple[ValidationShard, ...]
    gates: tuple[ValidationGate, ...]
    member_required: tuple[str, ...] = ()
    schedule_file: str = ""
    """Repository-relative scheduling weights, offered as {signetum.schedule_file}."""

    def __post_init__(self) -> None:
        if not self.shards or len(self.shards) != len({item.name for item in self.shards}):
            raise ManifestError("validation.shards must contain unique named shards")
        gates = {item.name for item in self.gates}
        if len(self.gates) != len(gates) or not {"member", "final"} <= gates:
            raise ManifestError("validation.gates must contain unique member and final gates")
        world = {item.name for item in self.shards if item.evidence == "world"}
        declared = {item.name for item in self.shards}
        for item in self.shards:
            unknown = sorted(set(item.after) - declared)
            if unknown:
                raise ManifestError(
                    f"{item.name} runs after undeclared shards: {', '.join(unknown)}"
                )
        member = next(item.shards for item in self.gates if item.name == "member")
        for origin, names in (("gates.member", member), ("member_required", self.member_required)):
            unknown = sorted(set(names) - declared)
            if unknown:
                raise ManifestError(
                    f"validation.{origin} names undeclared shards: {', '.join(unknown)}"
                )
            blocking = sorted(set(names) & world)
            if blocking:
                raise ManifestError(
                    f"validation.{origin} cannot depend on world state: {', '.join(blocking)}"
                )


@dataclass(frozen=True, kw_only=True)
class DeliveryBindings:
    branch: str

    def __post_init__(self) -> None:
        if not self.branch.strip():
            raise ManifestError("delivery branch must be nonempty")


@dataclass(frozen=True, kw_only=True)
class RepositoryManifest:
    schema_version: int
    signetum: SignetumIdentity
    profiles: ProfileSelection = field(default_factory=ProfileSelection)
    repository: RepositoryBindings
    delivery: DeliveryBindings | None = None
    impact: ImpactConfiguration = field(default_factory=ImpactConfiguration)
    validation: ValidationCommands

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ManifestError(f"unsupported manifest schema: {self.schema_version}")
        schedule = self.validation.schedule_file
        if schedule and schedule not in self.repository.lockfiles:
            raise ManifestError("validation.schedule_file must be listed in repository.lockfiles")
        if not schedule and any(SCHEDULE_FILE in shard.command for shard in self.validation.shards):
            raise ManifestError(f"placeholder {SCHEDULE_FILE} requires validation.schedule_file")


@dataclass(frozen=True, kw_only=True)
class ManifestBindings:
    """A manifest's identity and locations: where records live and what delivery targets."""

    signetum: SignetumIdentity
    repository: RepositoryBindings
    delivery: DeliveryBindings | None = None


def _require_schema(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ManifestError("manifest must be an object")
    version = data.get("schema_version")
    if type(version) is int and version > SCHEMA_VERSION:
        raise UnsupportedManifestError(f"unsupported manifest schema: {version}")
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ManifestError(f"unsupported manifest schema: {version}")
    return data


def _decode[T](model: type[T], data: object) -> T:
    try:
        return dataclass_from_mapping(model, data, use_defaults=True)
    except UnknownFieldsError as error:
        raise UnsupportedManifestError(str(error)) from error
    except (ValueError, TypeError, RecursionError) as error:
        raise ManifestError(str(error)) from error


def manifest_from_mapping(data: object) -> RepositoryManifest:
    return _decode(RepositoryManifest, _require_schema(data))


def parse_bindings(text: str) -> ManifestBindings:
    """Read only the identity, repository and delivery tables of a supported schema.

    Schema and protocol identity stay exact. Locating change records, decisions
    and the delivery branch needs nothing else, so a validation section this
    engine rejects, such as one an older engine wrote, does not stop the
    operation that admits its migration. No other table is read, interpreted or
    kept.
    """

    try:
        data = _require_schema(loads(text))
    except ManifestError:
        raise
    except (ValueError, TypeError, RecursionError) as error:
        raise ManifestError(str(error)) from error
    return _decode(
        ManifestBindings,
        {key: data[key] for key in ("signetum", "repository", "delivery") if key in data},
    )


def parse_manifest(text: str) -> RepositoryManifest:
    try:
        return manifest_from_mapping(loads(text))
    except ManifestError:
        raise
    except (ValueError, TypeError, RecursionError) as error:
        raise ManifestError(str(error)) from error


def _read(path: str | Path) -> str:
    source = Path(path)
    if source.name != "signetum.toml":
        raise ManifestError("active configuration must be named signetum.toml")
    try:
        return source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ManifestError(str(error)) from error


def load_manifest(path: str | Path) -> RepositoryManifest:
    return parse_manifest(_read(path))


def load_bindings(path: str | Path) -> ManifestBindings:
    return parse_bindings(_read(path))


__all__ = [
    "ImpactConfiguration",
    "ImpactRule",
    "ManifestBindings",
    "ManifestError",
    "ProfileSelection",
    "RepositoryBindings",
    "RepositoryManifest",
    "SignetumIdentity",
    "UnsupportedManifestError",
    "ValidationCommands",
    "ValidationGate",
    "ValidationShard",
    "ValidationTool",
    "load_bindings",
    "load_manifest",
    "manifest_from_mapping",
    "parse_bindings",
    "parse_manifest",
]
