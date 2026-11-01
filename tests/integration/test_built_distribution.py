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
from signetum.cli import app
from signetum.git import git_output
from signetum.runtime_identity import implementation_digest
from typer.core import TyperGroup
from typer.main import get_command

from tools.release import build_skill_archive

ROOT = Path(__file__).resolve().parents[2]


def test_built_wheel_ships_its_declared_resources_without_build_machine_facts(tmp_path):
    wheels = tuple((ROOT / "dist").glob("signetum-*.whl"))
    assert len(wheels) == 1
    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        assert "signetum/resources/schemas/signetum-v5.schema.json" in names
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


@pytest.fixture
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
    environment["MISE_DATA_DIR"] = environment.get(
        "MISE_DATA_DIR", str(Path.home() / ".local/share/mise")
    )
    environment["XDG_DATA_HOME"] = str(directory / "state")
    update = subprocess.run(  # noqa: S603 -- dependency-free update instructions
        [str(shutil.which("sh")), str(skill / "scripts/signetum"), "update"],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert update.returncode == 0, update.stderr
    assert (skill / json.loads(update.stdout)["reference"]).is_file()
    assert not (skill / ".runtime").exists()
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
        [str(shutil.which("sh")), str(skill / "scripts/signetum"), "setup"],
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
    invoke = ["mise", "exec", "--", "python", "-B"]
    command = json.dumps([*invoke, "-m", "unittest", "test_app.py"])
    prepare = json.dumps([*invoke, "-c", "pass"])
    manifest = f"""schema_version=5
[signetum]
protocol=2
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
"""
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
    identity = run("identity")
    assert identity["engine"]["implementation"] == prepared["engine"]["implementation"]
    assert identity["skill"]["content_digest"].startswith("sha256:")
    assert run("update")["automatic_updates"] is False
    if existing:
        instructions = skill / "SKILL.md"
        original_instructions = instructions.read_bytes()
        try:
            instructions.write_bytes(original_instructions + b"\n")
            revised = run("identity")
            assert revised["skill"]["content_digest"] != identity["skill"]["content_digest"]
            assert revised["engine"] == identity["engine"]
        finally:
            instructions.write_bytes(original_instructions)
    if existing:
        for retired in ("protocol", "validate"):
            assert run(retired, "--help", ok=False).returncode != 0
        assert (project / "AGENTS.md").is_symlink()
        # The installed launcher must expose every command advertised by its engine.
        help_result = run("--help", ok=False)
        assert help_result.returncode == 0, help_result.stderr
        command_group = get_command(app)
        assert isinstance(command_group, TyperGroup)
        for name in command_group.commands:
            assert name in help_result.stdout
            result = run(name, "--help", ok=False)
            assert result.returncode == 0, result.stdout + result.stderr
        for prefix in (("check", "manifest"),):
            assert run(*prefix, "--manifest", project / "signetum.toml")["status"] == "valid"

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
    run("change", "open", "arithmetic", cwd=member)
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
    assert run("test", "run", "--shard", "app:test", cwd=member, ok=False).returncode != 0
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
    assert (
        run("change", "current", cwd=project)["historical_authorities"]["mode"] == "read_on_demand"
    )
    (project / "signetum.toml").write_text(manifest.replace("protocol=2", "protocol=99"))
    assert run("status", cwd=project, ok=False).returncode != 0
    if existing:
        update_plan = tmp_path / "update-plan.json"
        update = run("adopt", "preview", "--request", request, "--output", update_plan)
        assert update["files"] == [{"path": "signetum.toml", "action": "replace"}]
        assert (
            run("adopt", "apply", "--plan", update_plan, "--expected-plan", update["plan_digest"])[
                "status"
            ]
            == "applied"
        )
        assert run("status")["status"] == "passed"
        assert all((project / name).read_bytes() == content for name, content in originals.items())

    # Engine cache corruption must refuse without repairing or reinstalling it.
    home = Path(prepared["environment"])
    marker = home / "installed.json"
    original_marker = marker.read_bytes()
    document = json.loads(original_marker)
    document["environment"] = "unreviewed"
    marker.write_text(json.dumps(document))
    try:
        refused = run("identity", ok=False)
        assert refused.returncode != 0
        assert "identity changed" in refused.stderr
        assert json.loads(marker.read_text())["environment"] == "unreviewed"
    finally:
        marker.write_bytes(original_marker)
    package = next((home / "environment/lib").glob("python*/site-packages/signetum/__init__.py"))
    original_package = package.read_bytes()
    package.write_bytes(original_package + b"\n# changed installed engine\n")
    try:
        refused = run("identity", ok=False)
        assert refused.returncode != 0
        assert "engine changed" in refused.stderr
        assert package.read_bytes() != original_package
    finally:
        package.write_bytes(original_package)

    if existing:
        before = (project / "signetum.toml").read_bytes()
        head = git_output(project, "rev-parse", "HEAD")
        status = git_output(project, "status", "--porcelain")
        candidate = tmp_path / "candidate"
        shutil.copytree(
            skill,
            candidate,
            ignore=shutil.ignore_patterns(".runtime", ".venv", "__pycache__", "*.pyc", "dist"),
        )
        source = candidate / "scripts/engine/signetum/__init__.py"
        source.write_bytes(source.read_bytes() + b"\n# compatible implementation update\n")
        assert run("update", "--check", "--source", candidate)["status"] == "available"
        updated = run("update", "--source", candidate)
        assert updated["status"] == "updated"
        assert skill.is_symlink()
        assert updated["project_changed"] is False
        assert (project / "signetum.toml").read_bytes() == before
        assert git_output(project, "rev-parse", "HEAD") == head
        assert git_output(project, "status", "--porcelain") == status
        assert run("identity")["engine"]["implementation"] != prepared["engine"]["implementation"]
        assert (
            run("check", "manifest", "--manifest", project / "signetum.toml")["status"] == "valid"
        )
        assert run("status")["status"] == "passed"
        previous_launcher = Path(updated["previous_entry"]) / "scripts/signetum"
        saved_launcher, launcher = launcher, previous_launcher
        assert run("identity")["engine"] == prepared["engine"]
        launcher = saved_launcher
        # A failed candidate preparation preserves the selected, usable installation.
        lock = candidate / "scripts/engine/uv.lock"
        lock.write_text("invalid lock content")
        selected = skill.resolve()
        assert run("update", "--source", candidate, ok=False).returncode != 0
        assert skill.resolve() == selected
        assert run("identity")["engine"]["implementation"] != prepared["engine"]["implementation"]

    # A prepared Skill must not select an application's older/missing Python.
    shim = tmp_path / "application-tools"
    shim.mkdir()
    mise = shim / "mise"
    mise.write_text("#!/bin/sh\necho 'application tool selection is forbidden' >&2\nexit 23\n")
    mise.chmod(0o755)
    environment["PATH"] = str(shim) + os.pathsep + environment["PATH"]
    assert run("identity")["engine"]["implementation"].startswith("sha256:")
