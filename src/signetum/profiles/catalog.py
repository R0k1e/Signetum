"""Portable immutable profile values, resource parsing and authority composition."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from tomllib import loads

from signetum.serialization import JsonValue, dataclass_from_mapping

PROFILE_RESOURCE_NAMES = (
    "shared-core-v1.toml",
    "python-default-v1.toml",
    "git-worktrunk-v1.toml",
)


class ProfileError(ValueError):
    """A selected profile set cannot be composed safely."""


class ProfileResourceError(ProfileError):
    """The maintained profile identity inputs could not be read."""


def _identity(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9-]*@[1-9][0-9]*", value) is None:
        raise ProfileError(f"profile identity must be immutable: {value}")
    return value


def validate_selection(
    selected: tuple[str, ...], replacements: Mapping[str, object] | None = None
) -> dict[str, str]:
    for identity in selected:
        _identity(identity)
    if len(selected) != len(set(selected)):
        raise ProfileError("profiles.enabled must contain unique identities")
    result = {}
    for target, replacement in (replacements or {}).items():
        source, substitute = _identity(target), _identity(replacement)
        if source == substitute:
            raise ProfileError("a profile cannot replace itself")
        result[source] = substitute
    return result


@dataclass(frozen=True)
class ProfileDeclaration:
    """One immutable policy profile declaration."""

    identity: str
    authorities: tuple[str, ...]
    requires: tuple[str, ...] = ()
    tools: tuple[dict[str, JsonValue], ...] = ()
    shards: tuple[dict[str, JsonValue], ...] = ()
    gates: tuple[dict[str, JsonValue], ...] = ()

    def __post_init__(self) -> None:
        _identity(self.identity)
        validate_selection(self.requires)
        if any(not value for value in self.authorities):
            raise ProfileError("profile authority identities must be non-empty")


def load_catalog(read_resource: Callable[[str], str]) -> dict[str, ProfileDeclaration]:
    """Parse only maintained catalog resources through their owned value types."""
    declarations = {}
    for name in PROFILE_RESOURCE_NAMES:
        try:
            document = loads(read_resource(name))
            version = document.pop("schema_version", None)
            if type(version) is not int or version != 1:
                raise ProfileError("unsupported profile resource schema")
            declaration = dataclass_from_mapping(ProfileDeclaration, document, use_defaults=True)
            if declaration.identity in declarations:
                raise ProfileError("duplicate profile resource identity")
            declarations[declaration.identity] = declaration
        except OSError as error:
            raise ProfileResourceError(f"profile resource unavailable: {name}: {error}") from error
        except (ValueError, RecursionError) as error:
            raise ProfileError(f"invalid profile resource {name}: {error}") from error
    return declarations


def resolve_profiles(
    selected: tuple[str, ...],
    *,
    catalog: Mapping[str, ProfileDeclaration],
    replacements: Mapping[str, object] | None = None,
) -> tuple[ProfileDeclaration, ...]:
    """Resolve only explicit selections and their declared dependencies."""
    configured_replacements = validate_selection(selected, replacements)
    available = dict(catalog)
    resolved: list[ProfileDeclaration] = []
    visiting: set[str] = set()
    authorities: set[str] = set()

    def add(identity: str, *, dependency: bool) -> None:
        declaration = available.get(identity)
        if declaration is None:
            label = "undeclared profile dependency" if dependency else "unsupported profile"
            raise ProfileError(f"{label}: {identity}")
        if declaration in resolved:
            return
        if identity in visiting:
            raise ProfileError(f"cyclic profile dependency: {identity}")
        visiting.add(identity)
        for requirement in declaration.requires:
            add(requirement, dependency=True)
        for authority in declaration.authorities:
            if authority in authorities:
                raise ProfileError(f"duplicate authority: {authority}")
            authorities.add(authority)
        visiting.remove(identity)
        resolved.append(declaration)

    unknown_targets = set(configured_replacements).difference(selected)
    if unknown_targets:
        raise ProfileError(f"replacement target is not enabled: {sorted(unknown_targets)[0]}")
    for identity in selected:
        add(configured_replacements.get(identity, identity), dependency=False)
    return tuple(resolved)
