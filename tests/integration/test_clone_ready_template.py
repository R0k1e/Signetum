import json
import subprocess
import sys
from pathlib import Path
from tomllib import loads

import pytest
from typer.testing import CliRunner

from signetum.cli import app
from signetum.template import TOP_LEVEL, render_template, validate_template

ROOT = Path(__file__).parents[2]


def test_template_is_minimal_and_clone_ready() -> None:
    report = validate_template(ROOT / "template")

    assert report.valid, report.problems
    assert {path.name for path in (ROOT / "template").iterdir()} == TOP_LEVEL
    assert "README.md" in report.files
    assert "README.zh-CN.md" in report.files
    assert "changes/.gitkeep" in report.files
    assert "signetum.yaml" not in report.files
    template_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "template").rglob("*")
        if path.is_file()
    )
    assert "uvx" not in template_text
    assert "signetum==" not in template_text


def test_template_enables_installable_python_default() -> None:
    manifest = (ROOT / "template/signetum.toml").read_text()
    toolchain = (ROOT / "template/mise.toml").read_text()
    project = (ROOT / "template/pyproject.toml").read_text()

    assert 'enabled = ["python-default@1", "git-worktrunk@1"]' in manifest
    assert 'python = "3.12.14"' in toolchain
    assert 'uv = "0.8.15"' in toolchain
    for tool in ("ruff", "ty", "pytest", "pip-audit", "detect-secrets"):
        assert tool in project
    assert (ROOT / "template/tests/unit/test_application.py").is_file()
    assert (ROOT / "template/tests/integration/test_application.py").is_file()


def test_template_executes_the_python_default_at_lifecycle_boundaries() -> None:
    lifecycle = loads((ROOT / "template/signetum.toml").read_text())
    workflow = (ROOT / "template/.github/workflows/ci.yml").read_text()

    shards = {item["name"]: item["command"] for item in lifecycle["validation"]["shards"]}
    gates = {item["name"]: item["shards"] for item in lifecycle["validation"]["gates"]}

    assert set(lifecycle["validation"]["member_required"]) == {
        "repository:diff",
        "repository:traceability",
        "python:unit",
        "python:secrets",
    }
    assert shards["python:ty"] == ["uv", "run", "--no-sync", "ty", "check", "src"]
    assert "python:integration" not in gates["member"]
    assert {"python:integration", "python:audit"}.issubset(gates["final"])
    assert "- run: uv sync --locked" in workflow
    assert (
        "- run: uv run --no-project python .agents/repo-dev/runtime/lifecycle.py final" in workflow
    )


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
    (source / "tools").mkdir()
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
        ("git", "config", "user.name", "Signetum test"),
        ("git", "config", "user.email", "signetum@example.invalid"),
        ("git", "add", "."),
        ("git", "commit", "-m", "initial template"),
        ("mise", "trust", "mise.toml"),
        ("mise", "install"),
        ("uv", "sync", "--locked"),
    ):
        subprocess.run(command, cwd=rendered, check=True, capture_output=True)

    # A repository which was not created by workspace-open adopts its base by
    # writing the record once, which is the documented migration path.
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=rendered,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    record = rendered / ".git/signetum/workspaces/main.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "branch": "main",
                "base": head,
                "kind": "batch",
                "members": [],
            }
        ),
        encoding="utf-8",
    )

    runtime = rendered / ".agents/repo-dev/runtime/lifecycle.py"
    diagnostic = subprocess.run(
        (sys.executable, "-I", str(runtime), "changed"),
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
    assert (rendered / "changes/first-change/review.toml").is_file()
    assert (rendered / "changes/first-change/specs/change.toml").is_file()
    assert (rendered / "changes/first-change/plans/change.md").is_file()
    assert duplicate.returncode == 2
    assert invalid.returncode == 2


def test_rendered_template_retains_and_reconciles_execution_deviations(tmp_path: Path) -> None:
    rendered = tmp_path / "repository"
    render_template(ROOT / "template", rendered)
    for command in (
        ("git", "init", "-b", "main"),
        ("git", "config", "user.name", "Signetum test"),
        ("git", "config", "user.email", "signetum@example.invalid"),
        (sys.executable, ".agents/repo-dev/runtime/change_open.py", "first-change"),
    ):
        subprocess.run(command, cwd=rendered, check=True, capture_output=True)
    specification = rendered / "changes/first-change/specs/change.toml"
    specification.write_text(
        specification.read_text(encoding="utf-8")
        .replace('status = "draft"', 'status = "approved"')
        .replace("implementation_authorized = false", "implementation_authorized = true"),
        encoding="utf-8",
    )
    runtime = rendered / ".agents/repo-dev/runtime/deviations.py"

    approval = subprocess.run(
        (sys.executable, "-I", str(runtime), "approval", "--change", "first-change"),
        cwd=rendered,
        check=True,
        capture_output=True,
        text=True,
    )
    recorded = subprocess.run(
        (
            sys.executable,
            "-I",
            str(runtime),
            "record",
            "--change",
            "first-change",
            "--id",
            "DEV-001",
            "--member",
            "impl/first-change",
            "--class",
            "implementation_clarification",
            "--summary",
            "The implementation authority is elsewhere.",
            "--commitment",
            "Preserve the approved behavior.",
            "--action",
            "Reuse the existing authority.",
            "--impact",
            "No public behavior changes.",
        ),
        cwd=rendered,
        check=True,
        capture_output=True,
        text=True,
    )
    resolved = subprocess.run(
        (
            sys.executable,
            "-I",
            str(runtime),
            "resolve",
            "--change",
            "first-change",
            "--id",
            "DEV-001",
            "--member",
            "impl/first-change",
            "--resolution",
            "no_authority_change",
            "--reason",
            "The approved behavior and authority are unchanged.",
        ),
        cwd=rendered,
        check=True,
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        (sys.executable, "-I", str(runtime), "status", "--change", "first-change"),
        cwd=rendered,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(approval.stdout)["status"] == "approval"
    assert json.loads(recorded.stdout)["status"] == "recorded"
    assert json.loads(resolved.stdout)["status"] == "resolved"
    assert json.loads(status.stdout)["deviation_count"] == 1
    assert not (rendered / ".signetum").exists()


def _traceability(
    repository: Path, changes_root: str = "changes"
) -> subprocess.CompletedProcess[str]:
    validator = repository / ".agents/repo-dev/runtime/traceability.py"
    return subprocess.run(
        (
            sys.executable,
            "-I",
            str(validator),
            "--repository",
            str(repository),
            "--changes-root",
            changes_root,
        ),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )


def test_rendered_template_accepts_the_complete_toml_example(tmp_path: Path) -> None:
    rendered = tmp_path / "repository"
    render_template(ROOT / "template", rendered)

    result = _traceability(rendered, "examples")

    assert result.returncode == 0
    assert '"valid": true' in result.stdout


@pytest.mark.parametrize(
    ("mutation", "issue"),
    [
        ("missing-plan", "missing-plan"),
        ("duplicate-owner", "duplicate-clause-owner"),
        ("unknown-clause", "unknown-review-clause"),
        ("uncovered-plan", "plan-missing-clause"),
        ("missing-deferral", "missing-specification"),
    ],
)
def test_rendered_template_rejects_broken_traceability(
    tmp_path: Path, mutation: str, issue: str
) -> None:
    rendered = tmp_path / "repository"
    render_template(ROOT / "template", rendered)
    example = rendered / "examples/complete-change"
    specification = example / "specs/greeting.toml"
    review = example / "review.toml"
    plan = example / "plans/greeting.md"

    if mutation == "missing-plan":
        plan.unlink()
    elif mutation == "duplicate-owner":
        duplicate = specification.read_text().replace(
            'id = "example-greeting/greeting"', 'id = "example-greeting/duplicate"'
        )
        (example / "specs/duplicate.toml").write_text(duplicate)
    elif mutation == "unknown-clause":
        specification.write_text(
            specification.read_text().replace('["EXAMPLE-001"]', '["UNKNOWN-001"]')
        )
    elif mutation == "uncovered-plan":
        plan.write_text(plan.read_text().replace("EXAMPLE-001", "OTHER-001"))
    else:
        review.write_text(
            review.read_text()
            .replace('disposition = "covered"', 'disposition = "deferred"')
            .replace(
                'specification = "example-greeting/greeting"',
                'specification = "missing/change"',
            )
        )

    result = _traceability(rendered, "examples")

    assert result.returncode == 3
    assert f'"code": "{issue}"' in result.stdout
