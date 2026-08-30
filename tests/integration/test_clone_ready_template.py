import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reposeal.cli import app
from reposeal.template import TOP_LEVEL, render_template, validate_template

ROOT = Path(__file__).parents[2]


def test_template_is_minimal_and_clone_ready() -> None:
    report = validate_template(ROOT / "template")

    assert report.valid, report.problems
    assert {path.name for path in (ROOT / "template").iterdir()} == TOP_LEVEL
    assert "README.md" in report.files
    assert "README.zh-CN.md" in report.files
    assert "changes/.gitkeep" in report.files
    template_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "template").rglob("*")
        if path.is_file()
    )
    assert "uvx" not in template_text
    assert "reposeal==" not in template_text


def test_template_render_has_identical_inventory(tmp_path: Path) -> None:
    source = ROOT / "template"
    rendered = tmp_path / "repository"

    source_report = validate_template(source)
    rendered_report = render_template(source, rendered)

    assert rendered_report.files == source_report.files
    assert (rendered / "README.md").read_text() == (source / "README.md").read_text()


def test_template_reports_missing_extra_forbidden_and_symlink(tmp_path: Path) -> None:
    source = tmp_path / "template"
    source.mkdir()
    for name in TOP_LEVEL - {"README.md"}:
        path = source / name
        if "." in name and name not in {".agents", ".github"}:
            path.write_text("", encoding="utf-8")
        else:
            path.mkdir()
    (source / "src").mkdir()
    (source / "linked").symlink_to(source / "LICENSE")

    report = validate_template(source)

    assert not report.valid
    assert any(
        problem.startswith("missing top-level entries: README.md") for problem in report.problems
    )
    assert any("unexpected top-level entries" in problem for problem in report.problems)
    assert any("engine-only path" in problem for problem in report.problems)
    assert any("symlink is not allowed" in problem for problem in report.problems)


def test_render_refuses_invalid_source_and_existing_destination(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    with pytest.raises(ValueError, match="missing top-level entries"):
        render_template(invalid, tmp_path / "rendered")

    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(ValueError, match="destination already exists"):
        render_template(ROOT / "template", destination)


def test_template_cli_checks_and_renders(tmp_path: Path) -> None:
    runner = CliRunner()
    checked = runner.invoke(app, ["template", "check", "--source", str(ROOT / "template")])
    rendered = runner.invoke(
        app,
        [
            "template",
            "render",
            "--source",
            str(ROOT / "template"),
            "--destination",
            str(tmp_path / "rendered"),
        ],
    )

    assert checked.exit_code == 0
    assert rendered.exit_code == 0
    assert '"valid": true' in checked.stdout
    assert (tmp_path / "rendered" / "README.zh-CN.md").is_file()


def test_rendered_template_runs_without_the_engine_package(tmp_path: Path) -> None:
    rendered = tmp_path / "repository"
    render_template(ROOT / "template", rendered)
    for command in (
        ("git", "init", "-b", "main"),
        ("git", "config", "user.name", "RepoSeal test"),
        ("git", "config", "user.email", "reposeal@example.invalid"),
        ("git", "add", "."),
        ("git", "commit", "-m", "initial template"),
    ):
        subprocess.run(command, cwd=rendered, check=True, capture_output=True)

    runtime = rendered / ".agents/repo-dev/runtime/lifecycle.py"
    diagnostic = subprocess.run(
        (sys.executable, "-I", str(runtime), "changed", "HEAD"),
        cwd=rendered,
        check=True,
        capture_output=True,
        text=True,
    )
    final = subprocess.run(
        (sys.executable, "-I", str(runtime), "final"),
        cwd=rendered,
        check=True,
        capture_output=True,
        text=True,
    )

    assert '"status": "changed"' in diagnostic.stdout
    assert '"status": "final"' in final.stdout


def test_rendered_template_opens_one_safe_active_change(tmp_path: Path) -> None:
    rendered = tmp_path / "repository"
    render_template(ROOT / "template", rendered)
    scaffold = rendered / ".agents/repo-dev/runtime/change_open.py"

    opened = subprocess.run(
        (sys.executable, "-I", str(scaffold), "first-change"),
        cwd=rendered,
        check=True,
        capture_output=True,
        text=True,
    )
    duplicate = subprocess.run(
        (sys.executable, "-I", str(scaffold), "first-change"),
        cwd=rendered,
        check=False,
        capture_output=True,
        text=True,
    )
    invalid = subprocess.run(
        (sys.executable, "-I", str(scaffold), "../unsafe"),
        cwd=rendered,
        check=False,
        capture_output=True,
        text=True,
    )

    assert '"status": "opened"' in opened.stdout
    assert (rendered / "changes/first-change/review.yaml").is_file()
    assert (rendered / "changes/first-change/specs/change.yaml").is_file()
    assert (rendered / "changes/first-change/plans/change.md").is_file()
    assert duplicate.returncode == 2
    assert invalid.returncode == 2
