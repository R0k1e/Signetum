"""Installed-resource adapter for portable profile parsing and composition."""

from collections.abc import Mapping
from importlib.resources import files

from signetum.profiles.catalog import (
    ProfileDeclaration,
    ProfileError,
    ProfileResourceError,
    load_catalog,
)
from signetum.profiles.catalog import resolve_profiles as _resolve_profiles
from signetum.resources import profiles as profile_resources


def _catalog() -> dict[str, ProfileDeclaration]:
    resources = files(profile_resources)
    return load_catalog(lambda name: (resources / name).read_text(encoding="utf-8"))


def resolve_profiles(
    selected: tuple[str, ...],
    *,
    replacements: Mapping[str, str] | None = None,
    catalog: Mapping[str, ProfileDeclaration] | None = None,
) -> tuple[ProfileDeclaration, ...]:
    return _resolve_profiles(
        selected, replacements=replacements, catalog=_catalog() if catalog is None else catalog
    )


__all__ = ["ProfileDeclaration", "ProfileError", "ProfileResourceError", "resolve_profiles"]
