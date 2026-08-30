"""Protocols composing generic checks with repository-owned facts."""

from dataclasses import dataclass
from typing import Protocol

from reposeal.manifest import RepositoryManifest


@dataclass(frozen=True)
class CheckResult:
    """One immutable result returned by a repository adapter."""

    check: str
    passed: bool


class RepositoryAdapter(Protocol):
    """Downstream-owned behavior needed by a generic reposeal check."""

    def validate(self, architecture: str) -> CheckResult:
        """Validate repository facts through a downstream authority."""


def run_check(manifest: RepositoryManifest, adapter: RepositoryAdapter) -> CheckResult:
    """Pass a manifest-owned path to the downstream validation adapter."""

    return adapter.validate(manifest.repository.architecture)


__all__ = ["CheckResult", "RepositoryAdapter", "run_check"]
