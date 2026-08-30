"""Repository inventory and reference boundaries."""

from pathlib import Path, PurePosixPath
from shutil import which
from subprocess import CalledProcessError, run  # nosec B404
from typing import Protocol

from pydantic import Field

from reposeal.change.models import FrozenModel, require_relative_path


class TraceabilityManifest(FrozenModel):
    """Only repository-owned bindings needed by the traceability core."""

    schema_version: int = Field(ge=1)
    changes_root: str = "changes"
    decision_roots: tuple[str, ...] = ("docs/decisions",)
    legacy_roots: tuple[str, ...] = ()
    legacy_inventory: tuple[str, ...] = ()


class RepositoryInventory(FrozenModel):
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
        executable = which("git")
        if executable is None:
            raise OSError("git executable is unavailable")
        try:
            completed = run(  # nosec B603
                [
                    executable,
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ],
                cwd=repository,
                check=True,
                capture_output=True,
            )
        except CalledProcessError as error:
            raise OSError("Git repository inventory failed") from error
        paths = frozenset(item for item in completed.stdout.decode().split("\0") if item)
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
