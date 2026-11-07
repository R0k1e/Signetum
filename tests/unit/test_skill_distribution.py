"""Distribution keeps downloads bounded and owns only its own guard entry in host hooks."""

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from signetum import hosts

SCRIPTS = Path(__file__).parents[2] / "skills/signetum/scripts"


@pytest.fixture
def distribution(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("skill_distribution", SCRIPTS / "distribution.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_offline_or_unpublished_update_reports_without_changing_anything(
    distribution, monkeypatch, capsys
):
    def offline(url):
        raise OSError("offline")

    monkeypatch.setattr(distribution, "_read", offline)
    assert distribution.main(["update", "--check"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"

    def unpublished(url):
        raise distribution.urllib.error.HTTPError(url, 404, "missing", None, io.BytesIO())

    monkeypatch.setattr(distribution, "_tag", lambda requested: "v0.4.0")
    monkeypatch.setattr(distribution, "_read", unpublished)
    assert distribution.main(["update", "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "no_release"


@pytest.mark.parametrize(
    "arguments", [["update", "--to", "v0.3.3"], ["install"], ["install", "--host", "other"]]
)
def test_unknown_or_targetless_requests_are_refused(distribution, capsys, arguments):
    try:
        code = distribution.main(arguments)
    except SystemExit as refused:
        code = refused.code
    assert code == 2


@pytest.mark.parametrize("kind", ["escape", "symlink", "duplicate"])
def test_archive_rejects_unsafe_content(distribution, tmp_path, kind):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        name = "signetum/" + ("../escape" if kind == "escape" else "SKILL.md")
        info = zipfile.ZipInfo(name)
        if kind == "symlink":
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "content")
        if kind == "duplicate":
            with pytest.warns(UserWarning):
                archive.writestr(name, "duplicate")
    with pytest.raises(ValueError, match=r"escaping|symlink|duplicate"):
        distribution._extract(payload.getvalue(), tmp_path)


def test_guard_entries_are_added_once_replaced_and_removed_alone(tmp_path):
    skill = tmp_path / "skills/signetum"
    moved = tmp_path / "elsewhere/signetum"
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}
    document = {"model": "fixture", "hooks": {"PreToolUse": [other], "Stop": []}}
    added = hosts.with_guard(document, skill)
    assert added["hooks"]["PreToolUse"] == [other, hosts.guard_entry(skill)]
    assert hosts.with_guard(added, skill) is added
    assert hosts.runs_guard(added, skill) and not hosts.runs_guard(added, moved)
    relocated = hosts.with_guard(added, moved)
    assert relocated["hooks"]["PreToolUse"] == [other, hosts.guard_entry(moved)]
    assert hosts.without_guard(relocated) == document
    assert hosts.without_guard({"hooks": {"PreToolUse": [hosts.guard_entry(skill)]}}) == {}
    assert added["model"] == "fixture" and document["hooks"]["PreToolUse"] == [other]


@pytest.mark.parametrize("text", ["[]", "{", '{"hooks": []}', '{"hooks": {"PreToolUse": {}}}'])
def test_malformed_host_configuration_is_refused(tmp_path, text):
    path = tmp_path / "settings.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        hosts.read_config(path)
    assert hosts.read_config(tmp_path / "absent.json") == {}


def test_guard_notice_follows_the_skill_location_and_every_hook_source(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    project = tmp_path / "project"
    for host, project_file in (
        ("claude", ".claude/settings.local.json"),
        ("codex", ".codex/hooks.json"),
    ):
        skill = hosts.skills_dir(host) / "signetum"
        skill.mkdir(parents=True)
        notice = hosts.guard_notice(skill, project)
        assert notice is not None and notice["host"] == host
        assert notice["config"] == str(hosts.hook_config(host))
        assert notice["enable"].endswith(f"install --host {host}")
        assert notice["hook"] == {"hooks": {"PreToolUse": [hosts.guard_entry(skill)]}}
        target = project / project_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(hosts.with_guard({}, skill)))
        assert hosts.guard_notice(skill, project) is None
        target.unlink()
        hosts.hook_config(host).write_text(json.dumps(hosts.with_guard({}, skill)))
        assert hosts.guard_notice(skill, project) is None
    assert hosts.guard_notice(tmp_path / "agent/signetum", project) is None
    with pytest.raises(ValueError, match="unknown host"):
        hosts.host_home("other")


def test_traced_skill_copy_shares_environments_and_refuses_setup_while_in_use(tmp_path):
    """Drive the shipped runtime lock from the installed-skill path coverage traces."""

    scripts = tmp_path / "installed Skill" / "signetum" / "skills" / "signetum" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "installation.py").write_bytes((SCRIPTS / "installation.py").read_bytes())
    probe = tmp_path / "probe.py"
    probe.write_text(
        "\n".join(
            (
                "import sys",
                "sys.path.insert(0, sys.argv[1])",
                "import installation",
                "with installation.runtime_use('fingerprint'):",
                "    with installation.runtime_use('fingerprint'):",
                "        pass",
                "    try:",
                "        with installation.runtime_use('fingerprint', exclusive=True):",
                "            raise SystemExit('setup did not wait for commands')",
                "    except ValueError as error:",
                "        if 'in use' not in str(error):",
                "            raise",
                "print(installation.runtime_root())",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    env = dict(os.environ, XDG_DATA_HOME=str(tmp_path / "state"))
    completed = subprocess.run(  # noqa: S603 -- shipped installation module, explicit interpreter
        [sys.executable, str(probe), str(scripts)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == str(tmp_path / "state/signetum/runtime")
