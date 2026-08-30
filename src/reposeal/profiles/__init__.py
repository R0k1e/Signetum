"""Explicit profile resource loading and composition."""

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files

import yaml
from pydantic import BaseModel, ConfigDict, TypeAdapter

from reposeal.resources import profiles as profile_resources


class ProfileError(ValueError):
    """A selected profile set cannot be composed safely."""


@dataclass(frozen=True)
class ProfileDeclaration:
    """One immutable policy profile declaration."""

    identity: str
    authorities: tuple[str, ...]
    requires: tuple[str, ...] = ()


class _ProfileResource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    identity: str
    authorities: tuple[str, ...]
    requires: tuple[str, ...] = ()


_PROFILE_DOCUMENT = TypeAdapter(dict[str, object])
_RESOURCE_NAMES = (
    "shared-core-v1.yaml",
    "python-uv-v1.yaml",
    "git-worktrunk-v1.yaml",
)


def _catalog() -> dict[str, ProfileDeclaration]:
    declarations: dict[str, ProfileDeclaration] = {}
    for resource_name in _RESOURCE_NAMES:
        resource = files(profile_resources) / resource_name
        document = _PROFILE_DOCUMENT.validate_python(
            yaml.safe_load(resource.read_text(encoding="utf-8"))
        )
        parsed = _ProfileResource.model_validate(document)
        declaration = ProfileDeclaration(parsed.identity, parsed.authorities, parsed.requires)
        declarations[declaration.identity] = declaration
    return declarations


def resolve_profiles(
    selected: tuple[str, ...],
    *,
    catalog: Mapping[str, ProfileDeclaration] | None = None,
) -> tuple[ProfileDeclaration, ...]:
    """Resolve only selected profiles and their declared dependencies."""

    available = _catalog() if catalog is None else dict(catalog)
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

    for identity in selected:
        add(identity, dependency=False)
    return tuple(resolved)


__all__ = ["ProfileDeclaration", "ProfileError", "resolve_profiles"]
