"""Public invariants for check-only CI and exact-tree releases."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_ACTION = re.compile(r"- uses:\s+[^\s@]+@[0-9a-f]{40}(?:\s+#.*)?$")


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_ci_observes_one_read_only_triggering_commit() -> None:
    workflow = _read("ci.yml")
    assert "permissions:\n  contents: read" in workflow
    refs = re.findall(r"ref:\s+(.+)", workflow)
    assert refs and set(refs) == {"${{ github.sha }}"}
    mutation_commands = tuple(
        value
        for value in ("git commit", "git merge", "git push", "git branch -D")
        if value in workflow
    )
    assert mutation_commands == ()

    static_commands = (
        "uv run --no-sync ruff check .",
        "uv run --no-sync ruff format --check .",
        "uv run --no-sync ty check",
    )
    assert all(command in workflow for command in static_commands)


def test_reusable_actions_are_commit_pinned() -> None:
    action_lines = [
        line.strip()
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- uses:")
    ]
    assert action_lines
    assert all(PINNED_ACTION.fullmatch(line) for line in action_lines)


def test_release_validates_and_publishes_exact_tagged_tree() -> None:
    workflow = _read("release.yml")
    required = (
        "ref: ${{ github.sha }}",
        "uv sync --locked",
        "uv run --no-sync pytest",
        "uv build",
        "shasum -a 256 dist/*",
        "uv publish --trusted-publishing always",
        "gh release create",
    )
    assert all(value in workflow for value in required)


def test_retired_mutating_workflow_has_no_active_path() -> None:
    assert {path.name for path in WORKFLOWS.glob("*.yml")} == {
        "ci.yml",
        "release.yml",
    }
