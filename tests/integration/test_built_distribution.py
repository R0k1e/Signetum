"""A standard installed Skill owns execution, not consumer source or dependencies."""

import hashlib
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
from coverage import Coverage
from signetum.change_record import contract_digest, parse_change_record
from signetum.cli import app
from signetum.git import git_output
from signetum.runtime_identity import implementation_digest
from signetum.skill_identity import content_digest, skill_files
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


def _files(root: Path) -> dict[str, bytes]:
    """Installed content without interpreter bytecode caches."""

    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _copy_skill(destination: Path) -> Path:
    shutil.copytree(
        ROOT / "skills/signetum",
        destination,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", "dist"),
    )
    return destination


def _copy_plain(skill: Path, destination: Path) -> Path:
    shutil.copytree(skill, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return destination


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
    skill = _copy_skill(directory / "signetum")
    copied = _files(skill)
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
    assert _files(skill) == copied
    return skill, environment, prepared


def test_installed_launcher_coverage_combines_into_maintained_source(installed_skill, tmp_path):
    skill, environment, _ = installed_skill
    raw = tmp_path / "installed.coverage"
    result = subprocess.run(  # noqa: S603 -- real installed launcher and isolated coverage data
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--rcfile",
            str(ROOT / "pyproject.toml"),
            "--data-file",
            str(raw),
            "--source",
            str(skill / "scripts"),
            str(skill / "scripts/launch.py"),
            "identity",
        ],
        cwd=skill.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    collected = Coverage(data_file=str(raw), config_file=False)
    collected.combine(data_paths=[str(tmp_path)], strict=True, keep=True)
    collected.save()
    measured = collected.get_data()
    combined = Coverage(
        data_file=str(tmp_path / "combined.coverage"), config_file=str(ROOT / "pyproject.toml")
    )
    combined.combine(data_paths=[str(raw)], strict=True, keep=True)
    for name in ("launch.py", "installation.py"):
        installed = f"signetum/scripts/{name}"
        canonical = f"skills/signetum/scripts/{name}"
        lines = measured.lines(installed)
        assert lines, f"the real installed {name} must execute under coverage"
        assert set(lines) <= set(combined.get_data().lines(canonical) or ())
        assert installed not in combined.get_data().measured_files()
        assert (ROOT / canonical).is_file()
    combined.report(file=io.StringIO())


def test_installed_python_launcher_requires_preparation_and_rejects_changed_identity(
    installed_skill, tmp_path
):
    skill, original, expected = installed_skill
    environment = {**original, "XDG_DATA_HOME": str(tmp_path / "isolated state")}

    def launch(*arguments):
        return subprocess.run(  # noqa: S603 -- actual installed launcher, isolated runtime state
            [sys.executable, str(skill / "scripts/launch.py"), *arguments],
            cwd=skill.parent,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    refused = launch("identity")
    assert refused.returncode == 2
    assert "not prepared" in json.loads(refused.stderr)["cause"]
    prepared = launch("setup")
    assert prepared.returncode == 0, prepared.stderr
    observed = json.loads(prepared.stdout)
    assert observed["engine"]["implementation"] == expected["engine"]["implementation"]
    identity = launch("identity")
    assert identity.returncode == 0, identity.stderr
    assert json.loads(identity.stdout)["engine"] == observed["engine"]
    help_result = launch("--help")
    assert help_result.returncode == 0, help_result.stderr
    assert "workspace-open" in help_result.stdout
    receipt = Path(observed["environment"]) / "installed.json"
    record = json.loads(receipt.read_text())
    record["environment"] = "changed"
    receipt.write_text(json.dumps(record))
    changed = launch("identity")
    assert changed.returncode == 2
    assert "environment identity changed" in json.loads(changed.stderr)["cause"]
    repaired = launch("setup")
    assert repaired.returncode == 0, repaired.stderr
    assert json.loads(repaired.stdout)["engine"] == observed["engine"]


def test_copies_of_one_engine_share_one_environment_and_stay_unchanged(installed_skill, tmp_path):
    skill, environment, prepared = installed_skill
    other = _copy_skill(tmp_path / "host skills" / "signetum")
    before = _files(other)
    # Any agent tool installs the Skill folder on its own.
    plain = _copy_plain(skill, tmp_path / "agent skills" / "signetum")
    project = tmp_path / "project"
    project.mkdir()
    git_output(project, "init", "-b", "main")
    git_output(project, "config", "user.name", "Acceptance owner")
    git_output(project, "config", "user.email", "fixture@example.invalid")
    git_output(project, "commit", "--allow-empty", "-m", "test: start")
    for copy in (skill, other, plain):
        setup = _launch(copy, "setup", cwd=project, environment=environment)
        assert setup.returncode == 0, setup.stderr
        assert json.loads(setup.stdout.splitlines()[-1])["environment"] == prepared["environment"]
        identity = _launch(copy, "identity", cwd=project, environment=environment)
        assert identity.returncode == 0, identity.stderr
        observed = json.loads(identity.stdout.splitlines()[-1])
        assert observed["engine"] == prepared["engine"]
        status = _launch(copy, "status", cwd=project, environment=environment)
        assert status.returncode == 0, status.stdout + status.stderr
    assert _files(other) == before


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
            for name in ("CLAUDE.md", "Justfile", "package.json", ".claude/settings.json")
        }
    git_output(project, "add", ".")
    git_output(project, "commit", "-m", "test: initialize application")
    manifest = _manifest()
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
    assert (project / ".claude").exists() is existing
    assert not (project / ".codex").exists()
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
    batch = Path(
        run("batch-open", "--actor", "Owner", "--source", "Fixture approval", "--member", member)[
            "batch"
        ]
    )
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
if [ "$*" = "plugin list" ]; then cat "$CODEX_LIST"; fi
"""


class _Hosts:
    """A temporary home with fake host CLIs and one served release of a changed Skill."""

    def __init__(self, skill: Path, tmp_path: Path, monkeypatch, capsys, environment):
        for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT"):
            monkeypatch.delenv(key, raising=False)
        for key in ("MISE_DATA_DIR", "XDG_DATA_HOME"):
            monkeypatch.setenv(key, environment[key])
        cache = os.environ.get("UV_CACHE_DIR") or str(Path.home() / ".cache/uv")
        self.home = tmp_path / "home"
        self.claude = self.home / ".claude"
        self.codex = self.home / ".codex"
        self.claude.mkdir(parents=True)
        self.codex.mkdir()
        fakes = tmp_path / "hosts"
        fakes.mkdir()
        for name, script in (("claude", _FAKE_CLAUDE), ("codex", _FAKE_CODEX)):
            (fakes / name).write_text(script)
            (fakes / name).chmod(0o755)
        self.log = tmp_path / "hosts.log"
        self.log.touch()
        self.claude_list = tmp_path / "claude-list.json"
        self.claude_list.write_text("[]")
        self.codex_list = tmp_path / "codex-list.txt"
        self.codex_list.write_text("PLUGIN  STATUS\n")
        self.environment = dict(
            environment,
            HOME=str(self.home),
            CLAUDE_CONFIG_DIR=str(self.claude),
            CODEX_HOME=str(self.codex),
            UV_CACHE_DIR=cache,
            PATH=str(fakes) + os.pathsep + environment["PATH"],
            HOST_LOG=str(self.log),
            CLAUDE_LIST=str(self.claude_list),
            CODEX_LIST=str(self.codex_list),
        )
        for key in ("HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME", "UV_CACHE_DIR", "PATH"):
            monkeypatch.setenv(key, self.environment[key])
        for key in ("HOST_LOG", "CLAUDE_LIST", "CODEX_LIST"):
            monkeypatch.setenv(key, self.environment[key])
        self.project = tmp_path / "project"
        self.project.mkdir()
        git_output(self.project, "init", "-b", "main")
        git_output(self.project, "config", "user.name", "Acceptance owner")
        git_output(self.project, "config", "user.email", "fixture@example.invalid")
        (self.project / "signetum.toml").write_text(_manifest())
        git_output(self.project, "add", "signetum.toml")
        git_output(self.project, "commit", "-m", "test: adopt")
        monkeypatch.chdir(self.project)

        # The released candidate differs from the installed Skill only in its instructions.
        self.candidate = tmp_path / "candidate" / "signetum"
        shutil.copytree(skill, self.candidate, ignore=shutil.ignore_patterns("__pycache__"))
        instructions = self.candidate / "SKILL.md"
        instructions.write_bytes(instructions.read_bytes() + b"\n")
        self.version = parse_version(self.candidate)
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as bundle:
            for path in skill_files(self.candidate):
                bundle.write(path, "signetum/" + path.relative_to(self.candidate).as_posix())
        self.archive = buffer.getvalue()
        self.monkeypatch, self.capsys = monkeypatch, capsys

    def module(self, skill: Path):
        """Load distribution.py from one installed copy, as its launcher runs it."""

        self.monkeypatch.syspath_prepend(str(skill / "scripts"))
        self.monkeypatch.delitem(sys.modules, "installation", raising=False)
        name = "installed_distribution_" + str(abs(hash(skill)))
        spec = importlib.util.spec_from_file_location(name, skill / "scripts/distribution.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        self.monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        return module

    def serve(self, module, digest: str, *, version=None, archive=None) -> None:
        version = version or self.version
        tag = "v" + version
        metadata = json.dumps(
            {
                "release": {
                    "schema_version": 2,
                    "source": "c" * 40,
                    "components": [
                        {"name": "signetum-skill", "version": version, "digest": digest}
                    ],
                },
                "status": "valid",
            }
        ).encode()
        name = f"signetum-skill-{version}.zip"
        sums = "".join(
            f"{hashlib.sha256(content).hexdigest()}  dist/{file}\n"
            for file, content in ((name, self.archive), ("release-source.json", metadata))
        ).encode()
        documents = {
            module.LATEST: json.dumps({"tag_name": tag}).encode(),
            module.DOWNLOAD + tag + "/SHA256SUMS": sums,
            module.DOWNLOAD + tag + "/release-source.json": metadata,
            module.DOWNLOAD + tag + "/" + name: self.archive if archive is None else archive,
        }
        self.monkeypatch.setattr(module, "_read", documents.__getitem__)

    def run(self, module, *arguments: str) -> tuple[int, dict, list[str]]:
        mark = len(self.log.read_text().splitlines())
        code = module.main(list(arguments))
        calls = [
            line
            for line in self.log.read_text().splitlines()[mark:]
            if not line.endswith(("plugin list", "plugin list --json"))
        ]
        return code, json.loads(self.capsys.readouterr().out), calls


def _guard_payload(command: str, cwd: Path) -> str:
    return json.dumps({"cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": command}})


def test_install_places_the_skill_and_guard_for_each_host_and_reverses(
    installed_skill, tmp_path, monkeypatch, capsys
):
    skill, environment, _prepared = installed_skill
    hosts = _Hosts(skill, tmp_path, monkeypatch, capsys, environment)
    other_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}
    settings = hosts.claude / "settings.json"
    settings.write_text(
        json.dumps(
            {"permissions": {"allow": ["Bash(ls:*)"]}, "hooks": {"PreToolUse": [other_hook]}}
        )
    )
    codex_hooks = hosts.codex / "hooks.json"
    session = {"hooks": [{"type": "command", "command": "echo session"}]}
    codex_hooks.write_text(json.dumps({"hooks": {"SessionStart": [session]}}))
    hosts.claude_list.write_text(
        json.dumps(
            [
                {"id": "signetum@signetum", "scope": "user"},
                {"id": "signetum@signetum", "scope": "project", "projectPath": "/consumer"},
            ]
        )
    )
    hosts.codex_list.write_text("signetum@signetum  installed, enabled  0.4.0  /cache\n")
    installer = hosts.module(skill)
    configs = {path: path.read_bytes() for path in (settings, codex_hooks)}

    code, preview, calls = hosts.run(
        installer, "install", "--host", "claude", "--host", "codex", "--preview"
    )
    assert (code, preview["status"], calls) == (0, "previewed", [])
    assert [t["hook_action"] for t in preview["targets"]] == ["add", "add"]
    assert {path: path.read_bytes() for path in configs} == configs
    assert not (hosts.claude / "skills").exists() and not (hosts.codex / "skills").exists()

    code, result, calls = hosts.run(installer, "install", "--host", "claude", "--host", "codex")
    assert (code, result["status"]) == (0, "installed"), result
    placed = {
        host: home / "skills/signetum"
        for host, home in (("claude", hosts.claude), ("codex", hosts.codex))
    }
    assert all(content_digest(copy) == content_digest(skill) for copy in placed.values())
    claude = json.loads(settings.read_text())
    assert claude["permissions"] == {"allow": ["Bash(ls:*)"]}
    guard = result["targets"][0]["hook"]["hooks"][0]["command"]
    assert guard.endswith(str(placed["claude"].resolve() / "scripts/command-guard"))
    assert claude["hooks"]["PreToolUse"] == [
        other_hook,
        {"matcher": "Bash", "hooks": [{"type": "command", "command": guard, "timeout": 10}]},
    ]
    codex = json.loads(codex_hooks.read_text())
    assert codex["hooks"]["SessionStart"] == [session]
    assert len(codex["hooks"]["PreToolUse"]) == 1
    assert calls == [
        "claude plugin uninstall signetum@signetum --scope user",
        "codex plugin remove signetum@signetum",
    ]
    assert [(p["scope"], p["status"]) for p in result["plugins"]] == [
        ("user", "removed"),
        ("project", "manual"),
        ("user", "removed"),
    ]
    assert result["codex_hook_review_required"] is True

    # The registered command refuses through the installed copy only in adopted repositories.
    plain = tmp_path / "plain-repository"
    plain.mkdir()
    git_output(plain, "init", "-b", "main")
    for cwd, expected in ((hosts.project, 2), (plain, 0)):
        refused = subprocess.run(  # noqa: S603 -- the exact registered hook command
            ["/bin/sh", "-c", guard],
            input=_guard_payload("git stash", cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        assert refused.returncode == expected, refused.stderr

    hosts.claude_list.write_text("[]")
    hosts.codex_list.write_text("")
    configs = {path: path.read_bytes() for path in (settings, codex_hooks)}
    code, again, calls = hosts.run(installer, "install", "--host", "claude", "--host", "codex")
    assert (code, again["status"], calls) == (0, "unchanged", [])
    assert {path: path.read_bytes() for path in configs} == configs

    # A configured host gets no guidance; a host Skill without the hook gets one entry.
    status = _launch(placed["claude"], "status", cwd=hosts.project, environment=hosts.environment)
    assert status.returncode == 0, status.stderr
    assert "guard" not in json.loads(status.stdout.splitlines()[-1])
    code, result, _ = hosts.run(installer, "install", "--host", "claude", "--remove")
    assert (code, result["status"]) == (0, "removed")
    assert json.loads(settings.read_text()) == {
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {"PreToolUse": [other_hook]},
    }
    assert not placed["claude"].exists() and placed["codex"].exists()
    code, result, _ = hosts.run(installer, "install", "--skills-dir", str(hosts.claude / "skills"))
    assert (code, result["targets"][0]["skill_action"]) == (0, "place")
    status = _launch(placed["claude"], "status", cwd=hosts.project, environment=hosts.environment)
    assert status.returncode == 0, status.stderr
    notice = json.loads(status.stdout.splitlines()[-1])["guard"]
    assert notice["host"] == "claude"
    assert notice["enable"].endswith("install --host claude")
    assert notice["hook"]["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == guard
    outside = _launch(skill, "status", cwd=hosts.project, environment=hosts.environment)
    assert "guard" not in json.loads(outside.stdout.splitlines()[-1])

    # Refusals change nothing: foreign folders, Git work trees and malformed settings.
    foreign = tmp_path / "foreign"
    (foreign / "signetum").mkdir(parents=True)
    (foreign / "signetum/notes.txt").write_text("user work")
    tracked = tmp_path / "tracked"
    tracked.mkdir()
    git_output(tracked, "init", "-b", "main")
    for arguments in (["--skills-dir", str(foreign)], ["--skills-dir", str(tracked)]):
        code, result, _ = hosts.run(installer, "install", *arguments)
        assert (code, result["status"]) == (2, "failed")
    assert sorted(p.name for p in (foreign / "signetum").iterdir()) == ["notes.txt"]
    assert not (tracked / "signetum").exists()
    settings.write_text("[]")
    fresh = tmp_path / "fresh"
    code, result, _ = hosts.run(
        installer, "install", "--host", "claude", "--skills-dir", str(fresh)
    )
    assert (code, result["status"], settings.read_text()) == (2, "failed", "[]")
    assert not fresh.exists()

    # A published release installs only when its checksums and digest match.
    installer = hosts.module(skill)
    hosts.serve(installer, content_digest(hosts.candidate), archive=hosts.archive + b"tampered")
    code, result, _ = hosts.run(
        installer, "install", "--skills-dir", str(fresh), "--release", "latest"
    )
    assert (code, result["status"]) == (2, "failed")
    assert not (fresh / "signetum").exists()
    hosts.serve(installer, content_digest(hosts.candidate))
    code, result, _ = hosts.run(
        installer, "install", "--skills-dir", str(fresh), "--release", "latest"
    )
    assert (code, result["status"]) == (0, "installed"), result
    assert content_digest(fresh / "signetum") == content_digest(hosts.candidate)
    code, result, _ = hosts.run(
        installer, "install", "--skills-dir", str(fresh), "--source", str(skill)
    )
    assert (code, result["targets"][0]["skill_action"]) == (0, "replace")
    assert content_digest(fresh / "signetum") == content_digest(skill)


def test_update_replaces_the_skill_in_place_from_the_newest_release(
    installed_skill, tmp_path, monkeypatch, capsys
):
    skill, environment, _prepared = installed_skill
    hosts = _Hosts(skill, tmp_path, monkeypatch, capsys, environment)
    skills = hosts.claude / "skills"
    plain = _copy_plain(skill, skills / "signetum")
    settings = hosts.claude / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash"}]}}))
    configured = settings.read_bytes()
    original = content_digest(plain)
    updater = hosts.module(plain)

    def offline(url):
        raise OSError("offline")

    monkeypatch.setattr(updater, "_read", offline)
    code, result, _ = hosts.run(updater, "update", "--check")
    assert (code, result["status"]) == (2, "unavailable")

    hosts.serve(updater, "sha256:" + "0" * 64, version="0.0.1")
    code, result, calls = hosts.run(updater, "update")
    assert (code, result["status"], calls) == (0, "current", [])
    hosts.serve(updater, "sha256:" + "1" * 64)
    code, result, _ = hosts.run(updater, "update")
    assert (code, result["status"]) == (2, "failed")
    assert "differs from its release metadata" in result["cause"]
    hosts.serve(updater, content_digest(hosts.candidate), archive=hosts.archive + b"tampered")
    code, result, _ = hosts.run(updater, "update")
    assert (code, result["status"]) == (2, "failed")
    assert content_digest(plain) == original

    hosts.serve(updater, content_digest(hosts.candidate))
    code, result, _ = hosts.run(updater, "update", "--check")
    assert (code, result["status"]) == (0, "available")
    manifest = hosts.project / "signetum.toml"
    manifest.write_text(_manifest().replace("protocol=2", "protocol=99"))
    code, result, _ = hosts.run(updater, "update")
    assert (code, result["status"]) == (2, "migration_required")
    assert content_digest(plain) == original

    manifest.write_text(_manifest())
    code, result, calls = hosts.run(updater, "update")
    assert (code, result["status"], calls) == (0, "updated", []), result
    assert content_digest(plain) == content_digest(hosts.candidate)
    assert sorted(path.name for path in skills.iterdir()) == ["signetum"]
    assert settings.read_bytes() == configured
    identity = _launch(plain, "identity", cwd=hosts.project, environment=hosts.environment)
    assert identity.returncode == 0, identity.stderr
    observed = json.loads(identity.stdout.splitlines()[-1])["skill"]
    assert observed["content_digest"] == content_digest(hosts.candidate)
    code, result, _ = hosts.run(updater, "update")
    assert (code, result["status"]) == (0, "current")

    # A Skill folder that a repository tracks is updated through that repository.
    tracked = _copy_plain(skill, tmp_path / "project-skills" / "signetum")
    git_output(tracked.parent, "init", "-b", "main")
    before = content_digest(tracked)
    tracked_updater = hosts.module(tracked)
    hosts.serve(tracked_updater, content_digest(hosts.candidate))
    code, result, _ = hosts.run(tracked_updater, "update")
    assert (code, result["status"]) == (2, "failed")
    assert "Git work tree" in result["cause"]
    assert content_digest(tracked) == before
