"""Deterministic boundary for internal scaffold source material."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from signetum.runtime_generation import is_runtime_cache, runtime_problems

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
        "mise.toml",
        "pyproject.toml",
        "signetum.toml",
        "src",
        "tests",
        "uv.lock",
    }
)
FORBIDDEN_NAMES = frozenset({".claude", ".vscode", "profiles", "schemas", "skills", "tools"})


@dataclass(frozen=True)
class TemplateReport:
    """One stable validation result for a Template source tree."""

    files: tuple[str, ...]
    problems: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.problems


def validate_template(source: Path) -> TemplateReport:
    """Validate the exact scaffold surface without following symlinks."""
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
        if is_runtime_cache(relative):
            continue
        if path.is_symlink():
            problems.append(f"symlink is not allowed: {relative}")
        if any(part in FORBIDDEN_NAMES for part in relative.parts):
            problems.append(f"engine-only path is not allowed: {relative}")
        if path.is_file():
            files.append(relative.as_posix())
    problems.extend(runtime_problems(root))
    return TemplateReport(tuple(files), tuple(problems))


def render_template(source: Path, destination: Path) -> TemplateReport:
    """Copy a valid Template source into a new empty destination."""
    report = validate_template(source)
    if not report.valid:
        raise ValueError("; ".join(report.problems))
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    shutil.copytree(
        source,
        destination,
        symlinks=False,
        ignore=lambda directory, names: [name for name in names if is_runtime_cache(Path(name))],
    )
    rendered = validate_template(destination)
    if rendered.files != report.files or not rendered.valid:
        raise ValueError("rendered Template differs from its source inventory")
    return rendered
