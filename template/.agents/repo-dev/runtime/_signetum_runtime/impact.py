# Generated from signetum.impact; edit the engine source and regenerate.
"""Resolve actual repository changes against declared impact rules."""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol

from .evidence_receipts import ValidationSelection


class ImpactRuleLike(Protocol):
    """Normalized rule inputs supplied by a repository configuration adapter."""

    @property
    def name(self) -> str: ...

    @property
    def paths(self) -> tuple[str, ...]: ...

    @property
    def profiles(self) -> tuple[str, ...]: ...

    @property
    def gates(self) -> tuple[str, ...]: ...

    @property
    def shards(self) -> tuple[str, ...]: ...

    @property
    def requires_final(self) -> bool: ...


@dataclass(frozen=True)
class ImpactSelection:
    files: tuple[str, ...]
    rules: tuple[str, ...]
    profiles: tuple[str, ...]
    gates: tuple[str, ...]
    shards: tuple[str, ...]
    unexplained: tuple[str, ...]
    requires_final: bool


def select_impact(files: tuple[str, ...], rules: tuple[ImpactRuleLike, ...]) -> ImpactSelection:
    """Return a deterministic union of every rule matching the actual diff."""

    matched: list[ImpactRuleLike] = []
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


def select_paths(files: tuple[str, ...], rules: tuple[ImpactRuleLike, ...]) -> ValidationSelection:
    impact = select_impact(files, rules)
    encoded = json.dumps(files, separators=(",", ":")).encode()
    modified_tests = tuple(
        path
        for path in files
        if path.startswith("tests/") or "/tests/" in path or Path(path).name.startswith("test_")
    )
    reasons = tuple(f"impact rule {name} matched" for name in impact.rules)
    return ValidationSelection(
        changed_paths_digest="sha256:" + hashlib.sha256(encoded).hexdigest(),
        rules=impact.rules,
        profiles=impact.profiles,
        gates=impact.gates,
        shards=impact.shards,
        modified_tests=modified_tests,
        external_obligations=(),
        unexplained=impact.unexplained,
        requires_final=impact.requires_final,
        reasons=reasons,
    )


__all__ = ["ImpactRuleLike", "ImpactSelection", "select_impact", "select_paths"]
