"""A standard installed Skill owns execution, not consumer source or dependencies."""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile

import pytest
from signetum.change_record import contract_digest, parse_change_record
from signetum.cli import app
from signetum.git import git_output
from signetum.runtime_identity import implementation_digest
from signetum.skill_identity import content_digest, skill_files
from typer.core import TyperGroup
from typer.main import get_command

from tools.release import build_skill_archive, marketplace_pin

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


def parse_version(skill: Path) -> str:
    return tomllib.loads((skill / "scripts/engine/pyproject.toml").read_text())["project"][
        "version"
    ]


def _manifest() -> str:
    invoke = ["mise", "exec", "--", "python", "-B"]
    command = json.dumps([*invoke, "-m", "unittest", "test_app.py"])
    prepare = json.dumps([*invoke, "-c", "pass"])
    return f"""schema_version=5
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
shards=["app:test"]
[[validation.gates]]
name="final"
shards=["app:test"]
"""


def _plugin_files(root: Path) -> dict[str, bytes]:
    """Plugin content as a host hashes it, without interpreter bytecode caches."""

    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _copy_plugin(destination: Path) -> Path:
    shutil.copytree(
        ROOT / "plugins/signetum",
        destination,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", "dist"),
    )
    return destination / "skills/signetum"


def _launch(skill: Path, *arguments: str, cwd: Path, environment: dict[str, str]):
    return subprocess.run(  # noqa: S603 -- explicit disposable consumer invocation
        [str(shutil.which("sh")), str(skill / "scripts/signetum"), *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


@pytest.fixture
def installed_skill(tmp_path_factory):
    directory = tmp_path_factory.mktemp("installed Skill")
    plugin = directory / "signetum"
    skill = _copy_plugin(plugin)
    copied = _plugin_files(plugin)
    environment = dict(os.environ)
    for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(key, None)
    environment["MISE_DATA_DIR"] = environment.get(
        "MISE_DATA_DIR", str(Path.home() / ".local/share/mise")
    )
    environment["XDG_DATA_HOME"] = str(directory / "state")
    update = _launch(skill, "update", cwd=directory, environment=environment)
    assert update.returncode == 2
    assert "not prepared" in update.stderr
    launcher = skill / "scripts/launch.py"
    refused = subprocess.run(  # noqa: S603 -- explicit disposable consumer invocation
        [sys.executable, str(launcher), "identity"],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    result = _launch(skill, "setup", cwd=directory, environment=environment)
    assert result.returncode == 0, result.stderr
    prepared = json.loads(result.stdout.splitlines()[-1])
    assert prepared["engine"]["implementation"] == implementation_digest()
    assert Path(prepared["environment"]).is_relative_to(directory / "state/signetum/runtime")
    assert _plugin_files(plugin) == copied
    return skill, environment, prepared


def test_copies_of_one_engine_share_one_environment_and_leave_the_plugin_unchanged(
    installed_skill, tmp_path
):
    skill, environment, prepared = installed_skill
    other = _copy_plugin(tmp_path / "host cache" / "signetum" / "0.3.3")
    before = _plugin_files(other.parents[1])
    project = tmp_path / "project"
    project.mkdir()
    git_output(project, "init", "-b", "main")
    git_output(project, "config", "user.name", "Acceptance owner")
    git_output(project, "config", "user.email", "fixture@example.invalid")
    git_output(project, "commit", "--allow-empty", "-m", "test: start")
    for copy in (skill, other):
        setup = _launch(copy, "setup", cwd=project, environment=environment)
        assert setup.returncode == 0, setup.stderr
        assert json.loads(setup.stdout.splitlines()[-1])["environment"] == prepared["environment"]
        identity = _launch(copy, "identity", cwd=project, environment=environment)
        assert identity.returncode == 0, identity.stderr
        observed = json.loads(identity.stdout.splitlines()[-1])
        assert observed["engine"] == prepared["engine"]
        status = _launch(copy, "status", cwd=project, environment=environment)
        assert status.returncode == 0, status.stdout + status.stderr
    assert _plugin_files(other.parents[1]) == before


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
        (project / ".claude").mkdir()
        (project / ".claude/settings.json").write_text('{"permissions": {"allow": []}}\n')
        originals = {
            name: (project / name).read_bytes()
            for name in ("CLAUDE.md", "Justfile", "package.json")
        }
    git_output(project, "add", ".")
    git_output(project, "commit", "-m", "test: initialize application")
    manifest = _manifest()
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"manifest": manifest}))
    assert run("adopt", "inspect")["status"] == "inspected"
    plan = tmp_path / "plan.json"
    proposal = run("adopt", "preview", "--request", request, "--output", plan)
    assert proposal["files"] == [
        {"path": ".claude/settings.json", "action": "replace" if existing else "create"},
        {"path": ".codex/config.toml", "action": "create"},
        {"path": "signetum.toml", "action": "create"},
    ]
    assert (
        run("adopt", "apply", "--plan", plan, "--expected-plan", proposal["plan_digest"])["status"]
        == "applied"
    )
    assert all((project / name).read_bytes() == content for name, content in originals.items())
    assert not (project / ".agents").exists()
    assert not (project / ".venv").exists()
    claude = json.loads((project / ".claude/settings.json").read_text())
    assert claude["enabledPlugins"] == {"signetum@signetum": True}
    assert ("permissions" in claude) is existing
    assert "enabled = true" in (project / ".codex/config.toml").read_text()
    identity = run("identity")
    assert identity["engine"]["implementation"] == prepared["engine"]["implementation"]
    assert identity["skill"]["content_digest"].startswith("sha256:")
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
        ".claude",
        ".codex",
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

    # A prepared Skill must not select an application's older/missing Python.
    shim = tmp_path / "application-tools"
    shim.mkdir()
    mise = shim / "mise"
    mise.write_text("#!/bin/sh\necho 'application tool selection is forbidden' >&2\nexit 23\n")
    mise.chmod(0o755)
    environment["PATH"] = str(shim) + os.pathsep + environment["PATH"]
    assert run("identity")["engine"]["implementation"].startswith("sha256:")


_FAKE_CLAUDE = """#!/bin/sh
printf 'claude %s\\n' "$*" >> "$HOST_LOG"
if [ "$*" = "plugin list --json" ]; then cat "$CLAUDE_LIST"; fi
"""
_FAKE_CODEX = """#!/bin/sh
printf 'codex %s\\n' "$*" >> "$HOST_LOG"
if [ "$*" = "plugin list" ]; then
    printf 'PLUGIN  STATUS  VERSION  SOURCE\\n'
    printf 'signetum@signetum  installed, disabled  0.3.3  /cache/signetum\\n'
fi
if [ "$*" = "plugin add signetum@signetum" ]; then
    sed 's/^enabled = false$/enabled = true/' "$CODEX_HOME/config.toml" > "$CODEX_HOME/next"
    mv "$CODEX_HOME/next" "$CODEX_HOME/config.toml"
fi
"""


def test_update_upgrades_each_installed_host_through_its_plugin_manager(
    installed_skill, tmp_path, monkeypatch, capsys
):
    skill, environment, _prepared = installed_skill
    for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)
    for key in ("MISE_DATA_DIR", "XDG_DATA_HOME"):
        monkeypatch.setenv(key, environment[key])
    hosts = tmp_path / "hosts"
    hosts.mkdir()
    for name, script in (("claude", _FAKE_CLAUDE), ("codex", _FAKE_CODEX)):
        (hosts / name).write_text(script)
        (hosts / name).chmod(0o755)
    log = tmp_path / "hosts.log"
    log.touch()
    listing = tmp_path / "claude-list.json"
    listing.write_text(json.dumps([{"id": "signetum@signetum", "scope": "project"}]))
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    user_config = (
        '[plugins."signetum@signetum"]\nenabled = false\n\n[mcp_servers.docs]\ncommand = "d"\n'
    )
    (codex_home / "config.toml").write_text(user_config)
    monkeypatch.setenv("PATH", str(hosts) + os.pathsep + environment["PATH"])
    monkeypatch.setenv("HOST_LOG", str(log))
    monkeypatch.setenv("CLAUDE_LIST", str(listing))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    project = tmp_path / "project"
    project.mkdir()
    git_output(project, "init", "-b", "main")
    (project / "signetum.toml").write_text(_manifest())
    monkeypatch.chdir(project)

    # The released candidate differs from the installed Skill only in its instructions.
    candidate = tmp_path / "candidate"
    shutil.copytree(skill, candidate, ignore=shutil.ignore_patterns("__pycache__"))
    (candidate / "SKILL.md").write_bytes((candidate / "SKILL.md").read_bytes() + b"\n")
    commit = "c" * 40
    archive = io.BytesIO()
    with ZipFile(archive, "w") as bundle:
        for path in skill_files(candidate):
            relative = path.relative_to(candidate).as_posix()
            bundle.write(path, f"Signetum-{commit}/plugins/signetum/skills/signetum/{relative}")
    version = parse_version(candidate)

    monkeypatch.syspath_prepend(str(skill / "scripts"))
    monkeypatch.delitem(sys.modules, "installation", raising=False)
    spec = importlib.util.spec_from_file_location("installed_update", skill / "scripts/update.py")
    assert spec is not None and spec.loader is not None
    updater = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, updater)
    spec.loader.exec_module(updater)

    def serve(digest: str) -> None:
        metadata = {
            "source": commit,
            "components": [{"name": "signetum-skill", "version": version, "digest": digest}],
        }
        documents = {
            updater.PIN: json.dumps(marketplace_pin(version, commit)).encode(),
            f"https://github.com/R0k1e/Signetum/releases/download/v{version}/"
            "release-source.json": json.dumps(metadata).encode(),
            f"https://codeload.github.com/R0k1e/Signetum/zip/{commit}": archive.getvalue(),
        }
        monkeypatch.setattr(updater, "_read", documents.__getitem__)

    def update() -> tuple[int, dict, list[str]]:
        mark = len(log.read_text().splitlines())
        code = updater.main([])
        upgrades = [
            line
            for line in log.read_text().splitlines()[mark:]
            if not line.endswith(("plugin list", "plugin list --json"))
        ]
        return code, json.loads(capsys.readouterr().out), upgrades

    serve(content_digest(candidate))
    code, result, upgrades = update()
    assert code == 0, result
    assert result["status"] == "updated"
    assert result["restart_required"] is True
    assert result["codex_hook_review_required"] is True
    assert upgrades == [
        "claude plugin marketplace update signetum",
        "claude plugin update signetum@signetum",
        "codex plugin marketplace upgrade signetum",
        "codex plugin add signetum@signetum",
    ]
    assert (codex_home / "config.toml").read_text() == user_config

    (project / "signetum.toml").write_text(_manifest().replace("protocol=2", "protocol=99"))
    code, result, upgrades = update()
    assert (code, result["status"], upgrades) == (2, "migration_required", [])

    (project / "signetum.toml").write_text(_manifest())
    listing.write_text("[]")
    code, result, upgrades = update()
    assert code == 0, result
    assert [item["host"] for item in result["upgraded"]] == ["codex"]
    assert upgrades == [
        "codex plugin marketplace upgrade signetum",
        "codex plugin add signetum@signetum",
    ]

    serve(content_digest(skill))
    mark = len(log.read_text().splitlines())
    code, result, _upgrades = update()
    assert (code, result["status"]) == (0, "current")
    assert log.read_text().splitlines()[mark:] == []
