"""A standard installed Skill owns execution, not consumer source or dependencies."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from signetum.change_record import contract_digest, parse_change_record
from signetum.git import git_output
from signetum.release import build_skill_archive
from signetum.runtime_identity import implementation_digest

ROOT = Path(__file__).resolve().parents[2]


def test_built_wheel_ships_its_declared_resources_without_build_machine_facts(tmp_path):
    wheels = tuple((ROOT / "dist").glob("signetum-*.whl"))
    assert len(wheels) == 1
    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        assert "signetum/resources/schemas/signetum-v4.schema.json" in names
        payload = b"\n".join(wheel.read(n) for n in names if n.endswith((".py", ".toml", ".json")))
    forbidden = (str(ROOT).encode(), b"/Users/", b".runtime/")
    assert all(value not in payload for value in forbidden)
    assert not any("vendor_yaml" in name or "/resources/skills/" in name for name in names)
    archive = build_skill_archive(ROOT, tmp_path)
    with ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert {
            "signetum/SKILL.md",
            "signetum/scripts/signetum",
            "signetum/scripts/engine/uv.lock",
        } <= names
        assert not any("/.runtime/" in name or "__pycache__" in name for name in names)


@pytest.fixture(scope="session")
def installed_skill(tmp_path_factory):
    directory = tmp_path_factory.mktemp("installed Skill")
    skill = directory / "signetum"
    shutil.copytree(
        ROOT / "skills/signetum",
        skill,
        ignore=shutil.ignore_patterns(".runtime", ".venv", "__pycache__", "*.pyc", "dist"),
    )
    environment = dict(os.environ)
    for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(key, None)
    launcher = skill / "scripts/launch.py"
    refused = subprocess.run(  # noqa: S603 -- explicit disposable consumer invocation
        [sys.executable, str(launcher), "identity"],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    result = subprocess.run(  # noqa: S603 -- explicit disposable consumer invocation
        [sys.executable, str(launcher), "setup"],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    prepared = json.loads(result.stdout.splitlines()[-1])
    assert prepared["engine"]["implementation"] == implementation_digest()
    assert Path(prepared["environment"]).is_relative_to(skill / ".runtime")
    return skill, environment, prepared


@pytest.mark.parametrize("existing", [False, True])
def test_installed_skill_adopts_and_delivers_without_entering_application(
    installed_skill, tmp_path, existing
):
    skill, environment, prepared = installed_skill
    project = tmp_path / "application"
    project.mkdir()
    environment = dict(environment, MISE_TRUSTED_CONFIG_PATHS=str(tmp_path))
    launcher = skill / "scripts/signetum"

    def run(*args, cwd=project, ok=True):
        result = subprocess.run(  # noqa: S603 -- explicit disposable consumer invocation
            [str(shutil.which("sh")), str(launcher), *map(str, args)],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if ok:
            assert result.returncode == 0, result.stdout + result.stderr
            return json.loads(result.stdout.splitlines()[-1])
        return result

    git_output(project, "init", "-b", "main")
    git_output(project, "config", "user.name", "Acceptance owner")
    git_output(project, "config", "user.email", "fixture@example.invalid")
    (project / "mise.toml").write_text('[tools]\nworktrunk="0.74.0"\n')
    (project / "app.py").write_text("def twice(value): return value * 3\n")
    (project / "test_app.py").write_text(
        "import unittest\nfrom app import twice\nclass Result(unittest.TestCase):\n"
        "    def test_result(self): self.assertEqual(twice(2),4)\n"
    )
    (project / ".gitignore").write_text("__pycache__/\n")
    originals = {}
    if existing:
        (project / "CLAUDE.md").write_text("Existing project authority.\n")
        (project / "AGENTS.md").symlink_to("CLAUDE.md")
        (project / "Justfile").write_text("test:\n    existing-tool\n")
        (project / "package.json").write_text('{"name":"existing-product"}\n')
        originals = {
            name: (project / name).read_bytes()
            for name in ("CLAUDE.md", "Justfile", "package.json")
        }
    git_output(project, "add", ".")
    git_output(project, "commit", "-m", "test: initialize application")
    invoke = ["mise", "exec", "--", "python"]
    command = json.dumps([*invoke, "-m", "unittest", "test_app.py"])
    prepare = json.dumps([*invoke, "-c", "pass"])
    manifest = f'''schema_version=4
[signetum]
protocol=2
engine_digest="{prepared["engine"]["implementation"]}"
[delivery]
branch="main"
[repository]
changes="changes"
decisions="docs/decisions"
[validation]
[[validation.shards]]
name="app:test"
command={command}
[[validation.shards]]
name="app:prepare"
command={prepare}
[[validation.gates]]
name="prepare"
shards=["app:prepare"]
[[validation.gates]]
name="member"
shards=["app:test"]
[[validation.gates]]
name="batch"
shards=[]
[[validation.gates]]
name="final"
shards=["app:test"]
'''
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"manifest": manifest}))
    assert run("adopt", "inspect")["status"] == "inspected"
    plan = tmp_path / "plan.json"
    proposal = run("adopt", "preview", "--request", request, "--output", plan)
    assert proposal["files"] == [{"path": "signetum.toml", "action": "create"}]
    assert (
        run("adopt", "apply", "--plan", plan, "--expected-plan", proposal["plan_digest"])["status"]
        == "applied"
    )
    assert all((project / name).read_bytes() == content for name, content in originals.items())
    assert not (project / ".agents").exists()
    assert not (project / ".venv").exists()
    if existing:
        assert (project / "AGENTS.md").is_symlink()
    git_output(project, "add", ".")
    git_output(project, "commit", "-m", "test: adopt reviewed bindings")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git_output(remote, "init", "--bare")
    git_output(project, "remote", "add", "origin", str(remote))
    git_output(project, "push", "origin", "main")
    base = git_output(project, "rev-parse", "HEAD")
    member = Path(run("workspace-open", "plan/arithmetic", base)["worktree"])
    assert member.is_relative_to(project / ".worktrees")
    run("change-open", "arithmetic", cwd=member)
    record = member / "changes/arithmetic/change.toml"
    text = f'''[change]
schema_version=1
id="arithmetic"
[change.source]
kind="human_direction"
summary="Acceptance fixture: correct arithmetic."
[change.contract]
version=1
approved_base="{base}"
[[change.contract.requirements]]
id="ARITH-001"
outcome="twice returns two times its argument"
acceptance=["The existing unittest passes."]
[[change.execution.steps]]
id="STEP-1"
requirements=["ARITH-001"]
action="Repair the arithmetic and retain its unittest."
'''
    digest = contract_digest(parse_change_record(text).contract)
    record.write_text(
        text
        + f'''\n[change.approval]
actor="Acceptance fixture owner"
recorded_at=2026-10-31
source="Explicit approval inside this disposable acceptance scenario."
contract_digest="{digest}"
'''
    )
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "test: approve fixture outcome")
    assert run("test", "--shard", "app:test", cwd=member, ok=False).returncode != 0
    (member / "app.py").write_text("def twice(value): return value * 2\n")
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "fix: correct arithmetic")
    assert run("ready", cwd=member)["status"] == "passed"
    hook = project / ".git/hooks/commit-msg"
    hook.write_text(
        '#!/bin/sh\ncase "$(head -n 1 "$1")" in\n  "Merge "*) exit 0;;\n'
        '  *) echo "project commit policy refused" >&2; exit 1;;\nesac\n'
    )
    hook.chmod(0o755)
    batch = Path(run("batch-open", "--member", member)["batch"])
    assert git_output(batch, "rev-list", "--count", "--first-parent", f"{base}..HEAD") == "1"
    result = run("final", cwd=batch)
    assert result["status"] == "passed"
    delivered = run("batch-deliver", batch, project, base, result["source"], cwd=batch)
    assert delivered["status"] == "passed"
    assert git_output(project, "status", "--porcelain") == ""
    assert not (project / ".agents").exists()
    archive = tmp_path / "application.zip"
    subprocess.run(  # noqa: S603 -- explicit disposable consumer invocation
        [
            str(shutil.which("git")),
            "-C",
            str(project),
            "archive",
            "--format=zip",
            "-o",
            str(archive),
            "HEAD",
        ],
        check=True,
    )
    with ZipFile(archive) as bundle:
        top = {name.split("/", 1)[0] for name in bundle.namelist()}
    assert top <= {
        "app.py",
        "test_app.py",
        ".gitignore",
        "mise.toml",
        "signetum.toml",
        "changes",
        *originals,
        "AGENTS.md",
    }
    assert run("current", cwd=project)["historical_authorities"]["mode"] == "read_on_demand"
    (project / "signetum.toml").write_text(
        manifest.replace(prepared["engine"]["implementation"], "sha256:" + "0" * 64)
    )
    assert run("status", cwd=project, ok=False).returncode != 0
