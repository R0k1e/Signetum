"""Portable typed Signetum repository configuration boundary."""

from dataclasses import dataclass, field, fields
from pathlib import Path
from re import fullmatch
from tomllib import loads

from signetum.profiles.catalog import validate_selection
from signetum.resources.schemas import evidence_schema_digest as published_evidence_schema_digest
from signetum.selection_contracts import SelectionProvider, repository_file
from signetum.serialization import UnknownFieldsError, dataclass_from_mapping
from signetum.validation import GateDeclaration as ValidationGate
from signetum.validation import ToolDeclaration as ValidationTool
from signetum.validation import ValidationShard

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


def _require_acyclic_coverage(covers: dict[str, tuple[str, ...]]) -> None:
    finished: set[str] = set()

    def visit(name: str, path: tuple[str, ...]) -> None:
        if name in path:
            raise ManifestError("cyclic shard coverage: " + " -> ".join((*path, name)))
        if name in finished:
            return
        for covered in covers.get(name, ()):
            visit(covered, (*path, name))
        finished.add(name)

    for name in covers:
        visit(name, ())


@dataclass(frozen=True, kw_only=True)
class ValidationCommands:
    tools: tuple[ValidationTool, ...] = ()
    shards: tuple[ValidationShard, ...]
    gates: tuple[ValidationGate, ...]
    member_required: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.shards or len(self.shards) != len({item.name for item in self.shards}):
            raise ManifestError("validation.shards must contain unique named shards")
        gates = {item.name for item in self.gates}
        if len(self.gates) != len(gates) or not {"member", "final"} <= gates:
            raise ManifestError("validation.gates must contain unique member and final gates")
        world = {item.name for item in self.shards if item.evidence == "world"}
        declared = {item.name for item in self.shards}
        covers = {item.name: item.covers for item in self.shards}
        for name, covered in covers.items():
            unknown = sorted(set(covered) - declared)
            if unknown:
                raise ManifestError(f"{name} covers undeclared shards: {', '.join(unknown)}")
            outside = sorted(set(covered) & world)
            if outside:
                raise ManifestError(f"{name} covers non-tree shards: {', '.join(outside)}")
        _require_acyclic_coverage(covers)
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


def manifest_from_mapping(data: object) -> RepositoryManifest:
    if not isinstance(data, dict):
        raise ManifestError("manifest must be an object")
    version = data.get("schema_version")
    if type(version) is int and version > SCHEMA_VERSION:
        raise UnsupportedManifestError(f"unsupported manifest schema: {version}")
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ManifestError(f"unsupported manifest schema: {version}")
    try:
        return dataclass_from_mapping(RepositoryManifest, data, use_defaults=True)
    except UnknownFieldsError as error:
        raise UnsupportedManifestError(str(error)) from error
    except (ValueError, TypeError, RecursionError) as error:
        raise ManifestError(str(error)) from error


def parse_manifest(text: str) -> RepositoryManifest:
    try:
        return manifest_from_mapping(loads(text))
    except ManifestError:
        raise
    except (ValueError, TypeError, RecursionError) as error:
        raise ManifestError(str(error)) from error


def load_manifest(path: str | Path) -> RepositoryManifest:
    source = Path(path)
    if source.name != "signetum.toml":
        raise ManifestError("active configuration must be named signetum.toml")
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ManifestError(str(error)) from error
    return parse_manifest(text)


__all__ = [
    "ImpactConfiguration",
    "ImpactRule",
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
    "load_manifest",
    "manifest_from_mapping",
    "parse_manifest",
]
