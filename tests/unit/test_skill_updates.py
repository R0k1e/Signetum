"""Explicit plugin updates read one released pin and keep network and mutation bounded."""

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

from tools.release import marketplace_pin

SCRIPTS = Path(__file__).parents[2] / "plugins/signetum/skills/signetum/scripts"
COMMIT = "a" * 40
METADATA = "https://github.com/R0k1e/Signetum/releases/download/v0.4.0/release-source.json"


@pytest.fixture
def updater(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("skill_update", SCRIPTS / "update.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _serve(updater, monkeypatch, *, pin=None, metadata=None):
    pin = marketplace_pin("0.4.0", COMMIT) if pin is None else pin
    metadata = (
        {
            "source": COMMIT,
            "components": [
                {"name": "signetum-skill", "version": "0.4.0", "digest": "sha256:" + "b" * 64}
            ],
        }
        if metadata is None
        else metadata
    )

    def read(url):
        if url == updater.PIN:
            if pin == 404:
                raise updater.urllib.error.HTTPError(url, 404, "missing", None, io.BytesIO())
            return json.dumps(pin).encode()
        assert url == METADATA
        return json.dumps(metadata).encode()

    monkeypatch.setattr(updater, "_read", read)


def test_check_reads_the_released_pin_bound_to_its_metadata(updater, monkeypatch, tmp_path):
    monkeypatch.setattr(
        updater, "describe", lambda root: {"version": "0.3.3", "content_digest": "sha256:old"}
    )
    _serve(updater, monkeypatch, pin=404)
    assert updater.check(tmp_path)["status"] == "no_release"
    _serve(updater, monkeypatch)
    result = updater.check(tmp_path)
    assert result["status"] == "available"
    assert result["candidate"]["source"] == COMMIT
    _serve(updater, monkeypatch, metadata={"source": "c" * 40, "components": []})
    with pytest.raises(ValueError, match="differs from the marketplace pin"):
        updater.check(tmp_path)
    moving = json.loads(json.dumps(marketplace_pin("0.4.0", COMMIT)))
    moving["plugins"][0]["source"]["ref"] = "main"
    _serve(updater, monkeypatch, pin=moving)
    with pytest.raises(ValueError, match="exact Signetum release"):
        updater.check(tmp_path)


def test_offline_or_unpinned_update_fails_without_changing_anything(updater, monkeypatch, capsys):
    def offline(url):
        raise OSError("offline")

    monkeypatch.setattr(updater, "_read", offline)
    assert updater.main(["--check"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"
    assert updater.main([]) == 2
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "failed"
    assert failed["project_changed"] is False
    _serve(updater, monkeypatch, pin=404)
    assert updater.main([]) == 2
    assert "no released" in json.loads(capsys.readouterr().out)["cause"]


@pytest.mark.parametrize("option", [["--to", "v0.3.3"], ["--source", "."]])
def test_retired_install_modes_are_refused(updater, option):
    with pytest.raises(SystemExit) as refused:
        updater.main(option)
    assert refused.value.code == 2


@pytest.mark.parametrize("kind", ["escape", "symlink", "duplicate"])
def test_archive_rejects_unsafe_selected_content(updater, tmp_path, kind):
    payload = io.BytesIO()
    prefix = "repo/plugins/signetum/skills/signetum/"
    with zipfile.ZipFile(payload, "w") as archive:
        name = prefix + ("../escape" if kind == "escape" else "SKILL.md")
        info = zipfile.ZipInfo(name)
        if kind == "symlink":
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "content")
        if kind == "duplicate":
            with pytest.warns(UserWarning):
                archive.writestr(name, "duplicate")
    with pytest.raises(ValueError, match=r"escaping|symlink|duplicate"):
        updater._extract(payload.getvalue(), tmp_path)


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
