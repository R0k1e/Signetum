"""Explicit installation updates keep network and application mutation bounded."""

import importlib.util
import io
import json
import shutil
import stat
import subprocess
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


def _stage_switch(updater, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "state"))
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    monkeypatch.setattr(updater, "_invoke", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        updater, "describe", lambda root: {"version": "0.3.0", "content_digest": str(root)}
    )
    monkeypatch.setattr(updater, "_version_copy", lambda source, state: source)
    monkeypatch.setattr(updater, "_prepare", lambda *args: {})
    return candidate


def _installation(updater):
    return sys.modules[updater.entry_switch.__module__]


def test_in_use_version_does_not_block_entry_switch_and_keeps_old_bytes(
    updater, monkeypatch, tmp_path
):
    candidate = _stage_switch(updater, monkeypatch, tmp_path)
    old = tmp_path / "old-version"
    old.mkdir()
    (old / "sentinel").write_text("old")
    entry = tmp_path / "installed"
    entry.symlink_to(old, target_is_directory=True)
    with _installation(updater).installation_use(old):
        result = updater.install(entry, candidate, tmp_path)
    assert result["status"] == "updated"
    assert result["project_changed"] is False
    assert entry.resolve() == candidate.resolve()
    assert (old / "sentinel").read_text() == "old"
    assert result["previous_entry"] == str(old)


def test_concurrent_entry_switch_is_refused_without_moving_the_entry(
    updater, monkeypatch, tmp_path
):
    candidate = _stage_switch(updater, monkeypatch, tmp_path)
    old = tmp_path / "old-version"
    old.mkdir()
    entry = tmp_path / "installed"
    entry.symlink_to(old, target_is_directory=True)
    with _installation(updater).entry_switch(entry):
        with pytest.raises(ValueError, match="being switched"):
            updater.install(entry, candidate, tmp_path)
    assert entry.resolve() == old.resolve()


def test_failed_switch_restores_symlink_and_loose_directory(updater, monkeypatch, tmp_path):
    candidate = _stage_switch(updater, monkeypatch, tmp_path)
    old = tmp_path / "old-version"
    old.mkdir()
    (old / "sentinel").write_text("old")
    entry = tmp_path / "installed"
    entry.symlink_to(old, target_is_directory=True)
    replace = updater.os.replace

    def fail_switch(source, target):
        if Path(source).is_symlink():
            raise OSError("switch refused")
        replace(source, target)

    monkeypatch.setattr(updater.os, "replace", fail_switch)
    with pytest.raises(OSError, match="switch refused"):
        updater.install(entry, candidate, tmp_path)
    assert entry.resolve() == old.resolve()
    assert (old / "sentinel").read_text() == "old"

    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "sentinel").write_text("loose")
    with pytest.raises(OSError, match="switch refused"):
        updater.install(loose, candidate, tmp_path)
    assert loose.is_dir() and not loose.is_symlink()
    assert (loose / "sentinel").read_text() == "loose"


def test_prepare_failure_does_not_switch_the_entry(updater, monkeypatch, tmp_path):
    candidate = _stage_switch(updater, monkeypatch, tmp_path)
    old = tmp_path / "old-version"
    old.mkdir()
    entry = tmp_path / "installed"
    entry.symlink_to(old, target_is_directory=True)

    def fail_prepare(*args):
        raise ValueError("prepare failed")

    monkeypatch.setattr(updater, "_prepare", fail_prepare)
    with pytest.raises(ValueError, match="prepare failed"):
        updater.install(entry, candidate, tmp_path)
    assert entry.resolve() == old.resolve()


def test_update_refuses_git_source_and_version_storage(updater, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "state"))
    source = tmp_path / "source"
    source.mkdir()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "sentinel").write_text("source")
    git = shutil.which("git")
    assert git is not None
    subprocess.run(  # noqa: S603 -- resolved Git executable, explicit init, no shell
        [git, "init", str(checkout)], check=True, capture_output=True
    )
    with pytest.raises(ValueError, match="Git-managed"):
        updater.install(checkout, source, tmp_path)
    assert (checkout / "sentinel").read_text() == "source"
    assert not checkout.is_symlink()

    stored = tmp_path / "state" / "signetum" / "versions" / "abc" / "signetum"
    stored.mkdir(parents=True)
    (stored / "sentinel").write_text("version")
    with pytest.raises(ValueError, match="version directory"):
        updater.install(stored, source, tmp_path)
    assert (stored / "sentinel").read_text() == "version"
    assert not stored.is_symlink()


def test_bare_update_installs_newer_exact_source_and_skips_current_or_older(
    updater, monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(
        updater,
        "describe",
        lambda root: {"version": "0.3.0", "content_digest": "sha256:" + "a" * 64},
    )
    installed = []
    commit = "c" * 40

    def install(entry, source, project):
        installed.append(source)
        return {"status": "updated", "entry": str(entry), "project_changed": False}

    monkeypatch.setattr(updater, "install", install)
    monkeypatch.setattr(
        updater, "_remote_source", lambda ref, destination: (destination / "skill", commit)
    )
    monkeypatch.setattr(
        updater,
        "latest_release",
        lambda: {"version": "0.4.0", "content_digest": "sha256:" + "b" * 64, "source": commit},
    )
    assert updater.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "updated"
    assert payload["source"] == commit
    assert payload["project_changed"] is False
    assert installed

    installed.clear()
    monkeypatch.setattr(
        updater,
        "latest_release",
        lambda: {"version": "0.4.0", "content_digest": "sha256:" + "a" * 64, "source": commit},
    )
    assert updater.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "current"
    monkeypatch.setattr(
        updater,
        "latest_release",
        lambda: {"version": "0.2.0", "content_digest": "sha256:" + "d" * 64, "source": commit},
    )
    assert updater.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "current"
    assert installed == []


def test_bare_update_network_or_missing_release_leaves_a_failed_result(
    updater, monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "state"))

    def offline():
        raise OSError("offline")

    monkeypatch.setattr(updater, "latest_release", offline)
    assert updater.main([]) == 2
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "failed"
    assert failed["project_changed"] is False
    monkeypatch.setattr(updater, "latest_release", lambda: None)
    assert updater.main([]) == 2
    missing = json.loads(capsys.readouterr().out)
    assert missing["status"] == "failed"
    assert "no stable" in missing["cause"]
