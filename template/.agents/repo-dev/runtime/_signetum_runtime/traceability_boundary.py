# Generated from signetum.traceability.boundary; edit the engine source and regenerate.
"""Repository inventory and reference boundaries."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Protocol

from .change_models import require_relative_path
from .contract_values import FrozenContract
from .git import GitError, GitInfrastructureError, git_output
from .serialization import Constraints


@dataclass(frozen=True, kw_only=True)
class TraceabilityManifest(FrozenContract):
    """Only repository-owned bindings needed by the traceability core."""

    schema_version: Annotated[int, Constraints(minimum=1)]
    changes_root: str = "changes"
    decision_roots: tuple[str, ...] = ("docs/decisions",)


@dataclass(frozen=True, kw_only=True)
class RepositoryInventory(FrozenContract):
    paths: frozenset[str]

    def contains(self, reference: str) -> bool:
        return str(require_relative_path(reference)) in self.paths

    def below(self, root: str) -> frozenset[str]:
        normalized = str(require_relative_path(root)).rstrip("/") + "/"
        return frozenset(path for path in self.paths if path.startswith(normalized))


class InventoryProvider(Protocol):
    def read(self, repository: Path) -> RepositoryInventory:
        """Read tracked and non-ignored untracked paths exactly once."""


class GitInventoryProvider:
    """Inventory adapter using Git's tracked/non-ignored path authority."""

    def read(self, repository: Path) -> RepositoryInventory:
        try:
            output = git_output(
                repository,
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                strip=False,
            )
        except GitInfrastructureError as error:
            raise OSError(str(error)) from error
        except GitError as error:
            raise OSError("Git repository inventory failed") from error
        paths = frozenset(item for item in output.split("\0") if item)
        return RepositoryInventory(paths=paths)


class ReferenceResolver:
    """Resolve only references present in the captured repository inventory."""

    def __init__(self, repository: Path, inventory: RepositoryInventory) -> None:
        self._repository = repository.resolve()
        self._inventory = inventory

    def resolve(self, reference: str) -> Path:
        normalized = str(require_relative_path(reference))
        if not self._inventory.contains(normalized):
            raise ValueError(f"reference is absent from repository inventory: {reference}")
        resolved = (self._repository / PurePosixPath(normalized)).resolve()
        if not resolved.is_relative_to(self._repository):
            raise ValueError(f"reference escapes repository: {reference}")
        return resolved
