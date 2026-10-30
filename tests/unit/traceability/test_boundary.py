from pathlib import Path

import pytest

from signetum import git
from signetum.git import GitError
from signetum.traceability import boundary
from signetum.traceability.boundary import (
    GitInventoryProvider,
    ReferenceResolver,
    RepositoryInventory,
)


def test_inventory_queries_git_once_and_decodes_nul_separated_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_inventory(*args: object, **kwargs: object) -> str:
        calls.append((*args, kwargs))
        return "a.txt\0docs/b.md\0"

    monkeypatch.setattr(boundary, "git_output", fake_inventory)

    inventory = GitInventoryProvider().read(tmp_path)

    assert inventory.paths == frozenset({"a.txt", "docs/b.md"})
    assert len(calls) == 1


def test_inventory_fails_when_git_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(git, "which", lambda executable: None)

    with pytest.raises(OSError, match="unavailable"):
        GitInventoryProvider().read(tmp_path)


def test_inventory_normalizes_git_failure_without_leaking_subprocess_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(*args: object, **kwargs: object) -> str:
        raise GitError("fixture inventory failed")

    monkeypatch.setattr(boundary, "git_output", fail)

    with pytest.raises(OSError, match="repository inventory failed"):
        GitInventoryProvider().read(tmp_path)


def test_inventory_and_resolver_enforce_declared_relative_paths(tmp_path: Path) -> None:
    document = tmp_path / "docs" / "contract.md"
    document.parent.mkdir()
    document.write_text("contract", encoding="utf-8")
    inventory = RepositoryInventory(paths=frozenset({"docs/contract.md", "docs/other.md"}))
    resolver = ReferenceResolver(tmp_path, inventory)

    assert inventory.contains("docs/contract.md")
    assert inventory.below("docs") == frozenset({"docs/contract.md", "docs/other.md"})
    assert resolver.resolve("docs/contract.md") == document
    with pytest.raises(ValueError, match="absent"):
        resolver.resolve("docs/missing.md")
    with pytest.raises(ValueError, match="relative"):
        resolver.resolve("../outside.md")
