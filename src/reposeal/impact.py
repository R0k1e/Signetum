"""Resolve actual repository changes against declared impact rules."""

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatch

from reposeal.manifest import ImpactRule


@dataclass(frozen=True)
class ImpactSelection:
    files: tuple[str, ...]
    rules: tuple[str, ...]
    profiles: tuple[str, ...]
    gates: tuple[str, ...]
    shards: tuple[str, ...]
    unexplained: tuple[str, ...]
    requires_final: bool


def select_impact(files: tuple[str, ...], rules: tuple[ImpactRule, ...]) -> ImpactSelection:
    """Return a deterministic union of every rule matching the actual diff."""

    matched: list[ImpactRule] = []
    unexplained: list[str] = []
    for changed_path in files:
        path_rules = tuple(
            rule for rule in rules if any(_matches(changed_path, pattern) for pattern in rule.paths)
        )
        if not path_rules:
            unexplained.append(changed_path)
        for rule in path_rules:
            if rule not in matched:
                matched.append(rule)
    return ImpactSelection(
        files=files,
        rules=tuple(rule.name for rule in matched),
        profiles=_ordered_union(rule.profiles for rule in matched),
        gates=_ordered_union(rule.gates for rule in matched),
        shards=_ordered_union(rule.shards for rule in matched),
        unexplained=tuple(unexplained),
        requires_final=bool(unexplained) or any(rule.requires_final for rule in matched),
    )


def _matches(path: str, pattern: str) -> bool:
    return fnmatch(path, pattern) or (
        pattern.endswith("/**") and path == pattern.removesuffix("/**")
    )


def _ordered_union(groups: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
    values: list[str] = []
    for group in groups:
        for value in group:
            if value not in values:
                values.append(value)
    return tuple(values)


__all__ = ["ImpactSelection", "select_impact"]
