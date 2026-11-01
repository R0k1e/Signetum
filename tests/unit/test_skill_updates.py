"""Explicit installation updates keep network and application mutation bounded."""

import importlib.util
import io
import json
import stat
import sys
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def updater(monkeypatch):
    scripts = Path(__file__).parents[2] / "skills/signetum/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("skill_update", scripts / "update.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_release_check_distinguishes_missing_offline_and_eligible(updater, monkeypatch, tmp_path):
    monkeypatch.setattr(
        updater, "describe", lambda root: {"version": "0.3.0", "content_digest": "old"}
    )
    monkeypatch.setattr(updater, "_read", lambda url: b'[{"assets":[]}]')
    assert updater.check(tmp_path, None)["status"] == "no_release"
    metadata_url = "https://github.com/R0k1e/Signetum/releases/download/v0.3.0/release-source.json"
    release: list[dict] = [
        {"assets": [{"name": "release-source.json", "browser_download_url": metadata_url}]}
    ]
    metadata = {
        "source": "a" * 40,
        "components": [
            {"name": "signetum-skill", "version": "0.3.0", "digest": "sha256:" + "b" * 64}
        ],
    }
    monkeypatch.setattr(
        updater,
        "_read",
        lambda url: json.dumps(metadata if url == metadata_url else release).encode(),
    )
    assert updater.check(tmp_path, None)["status"] == "available"
    release[0]["prerelease"] = True
    assert updater.check(tmp_path, None)["status"] == "no_release"

    def offline(url):
        raise OSError("offline")

    monkeypatch.setattr(updater, "_read", offline)
    assert updater.main(["--check"]) == 2


@pytest.mark.parametrize("kind", ["escape", "symlink", "duplicate"])
def test_archive_rejects_unsafe_selected_content(updater, tmp_path, kind):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        name = (
            "repo/skills/signetum/../escape"
            if kind == "escape"
            else "repo/skills/signetum/SKILL.md"
        )
        info = zipfile.ZipInfo(name)
        if kind == "symlink":
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "content")
        if kind == "duplicate":
            with pytest.warns(UserWarning):
                archive.writestr(name, "duplicate")
    with pytest.raises(ValueError, match=r"escaping|symlink|duplicate"):
        updater._extract(payload.getvalue(), tmp_path)


def test_active_installation_refuses_switch_and_failed_switch_restores_directory(
    updater, monkeypatch, tmp_path
):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "state"))
    entry = tmp_path / "installed"
    entry.mkdir()
    (entry / "sentinel").write_text("old")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    monkeypatch.setattr(updater, "_invoke", lambda *args, **kwargs: {})
    monkeypatch.setattr(updater, "describe", lambda root: {"content_digest": str(root)})
    monkeypatch.setattr(updater, "_version_copy", lambda source, state: source)
    monkeypatch.setattr(updater, "_prepare", lambda *args: {})
    with updater.installation_use(entry):
        with pytest.raises(ValueError, match="in use"):
            updater.install(entry, candidate, tmp_path)
    replace = updater.os.replace

    def fail_switch(source, target):
        if source.is_symlink():
            raise OSError("switch refused")
        replace(source, target)

    monkeypatch.setattr(updater.os, "replace", fail_switch)
    with pytest.raises(OSError, match="switch refused"):
        updater.install(entry, candidate, tmp_path)
    assert entry.is_dir() and not entry.is_symlink()
    assert (entry / "sentinel").read_text() == "old"
