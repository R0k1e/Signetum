"""Deterministic boundary for the public clone-ready Template tree."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

TOP_LEVEL = frozenset(
    {
        ".agents",
        ".github",
        ".gitignore",
        "AGENTS.md",
        "Justfile",
        "LICENSE",
        "README.md",
        "README.zh-CN.md",
        "changes",
        "docs",
        "examples",
        "mise.toml",
        "reposeal.yaml",
    }
)
FORBIDDEN_NAMES = frozenset(
    {".claude", ".vscode", "profiles", "schemas", "skills", "src", "tests", "tools"}
)


@dataclass(frozen=True)
class TemplateReport:
    """One stable validation result for a Template source tree."""

    files: tuple[str, ...]
    problems: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.problems


def validate_template(source: Path) -> TemplateReport:
    """Validate the exact public surface without following symlinks."""
    root = source.resolve()
    problems: list[str] = []
    actual = {path.name for path in root.iterdir()}
    if actual != TOP_LEVEL:
        missing = sorted(TOP_LEVEL - actual)
        extra = sorted(actual - TOP_LEVEL)
        if missing:
            problems.append(f"missing top-level entries: {', '.join(missing)}")
        if extra:
            problems.append(f"unexpected top-level entries: {', '.join(extra)}")

    files: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            problems.append(f"symlink is not allowed: {relative}")
        if any(part in FORBIDDEN_NAMES for part in relative.parts):
            problems.append(f"engine-only path is not allowed: {relative}")
        if path.is_file():
            files.append(relative.as_posix())
    return TemplateReport(tuple(files), tuple(problems))


def render_template(source: Path, destination: Path) -> TemplateReport:
    """Copy a valid Template source into a new empty destination."""
    report = validate_template(source)
    if not report.valid:
        raise ValueError("; ".join(report.problems))
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    shutil.copytree(source, destination, symlinks=False)
    rendered = validate_template(destination)
    if rendered.files != report.files or not rendered.valid:
        raise ValueError("rendered Template differs from its source inventory")
    return rendered
