"""Native ownership observation finds detached children and preserves unrelated jobs."""

import importlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from signetum.validation import process_observation


@pytest.fixture
def observer(request, monkeypatch):
    if getattr(request, "param", "engine") == "engine":
        return process_observation
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[3] / "tests/fixtures/portable-python/.agents/signetum/runtime")
    )
    return importlib.import_module("_signetum_runtime.process_observation")


@pytest.mark.parametrize("observer", ["engine", "template"], indirect=True)
def test_native_observation_finds_only_owned_detached_processes(observer, monkeypatch):
    if sys.platform != "darwin" and not sys.platform.startswith("linux"):
        pytest.skip("native process observation supports Linux and macOS")
    owner = uuid.uuid4().hex
    foreign_owner = uuid.uuid4().hex
    processes = []

    def spawn(token):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            env=dict(
                os.environ,
                SIGNETUM_PROCESS_OWNERS=json.dumps(
                    [
                        *observer.owner_tokens(os.environ.get(observer.OWNER_ENV, "[]")),
                        token,
                    ]
                ),
            ),
            start_new_session=True,
        )
        processes.append(process)
        return process

    try:
        root = spawn(owner)
        detached = spawn(owner)
        unrelated = spawn(foreign_owner)
        identity = observer.process_identity(detached.pid)
        assert identity.pid == detached.pid and identity.session == detached.pid
        assert identity.started > 0 and identity.uid == os.getuid()
        assert observer.process_owner_tokens(detached.pid)[-1] == owner
        found = observer.observe_owned_processes(owner, root.pid)
        assert {item.identity.pid for item in found.owned} == {detached.pid}
        assert found.owned[0].ownership == "owner-token"
        assert found.unavailable == ()
        assert unrelated.poll() is None
        root.terminate()
        root.wait(timeout=5)
        orphaned = observer.observe_owned_processes(owner, root.pid)
        assert {item.identity.pid for item in orphaned.owned} == {detached.pid}
        assert unrelated.poll() is None
        # A process inventory may transiently omit an existing detached child.
        # One empty snapshot must not qualify a clean settlement.
        inventory = observer._process_pids
        first = True

        def transient_inventory():
            nonlocal first
            pids = inventory()
            if first:
                first = False
                return tuple(pid for pid in pids if pid != detached.pid)
            return pids

        monkeypatch.setattr(observer, "_process_pids", transient_inventory)
        settled = observer.settle_owned_processes(owner, root.pid)
        assert settled.leaked == (detached.pid,)
        assert settled.remaining == ()
        assert settled.unavailable == ()
        assert unrelated.poll() is None
        detached.wait(timeout=5)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)


def test_linux_stat_parser_preserves_identity_with_parentheses_in_process_names(tmp_path, observer):
    directory = tmp_path / "123"
    directory.mkdir()
    fields = ["S", "1", "2", "301", *(["0"] * 15), "987"]
    (directory / "stat").write_text("123 (name with ) parentheses) " + " ".join(fields))
    identity = observer._linux_identity(123, tmp_path)
    assert (identity.pid, identity.session, identity.started) == (123, 301, 987)


@pytest.mark.parametrize("data", ["invalid", "123 (short) S 1", "123 (bad) S x x bad"])
def test_invalid_linux_metadata_is_not_an_empty_success(tmp_path, observer, data):
    directory = tmp_path / "123"
    directory.mkdir()
    (directory / "stat").write_text(data)
    with pytest.raises(observer.ProcessObservationUnavailable):
        observer._linux_identity(123, tmp_path)


@pytest.mark.parametrize("value", ["not-json", "{}", "[true]", '["invalid-owner"]'])
def test_invalid_ownership_markers_never_authorize_a_process(observer, value):
    assert observer.owner_tokens(value) == ()


def test_unsupported_hosts_are_explicit_instead_of_reporting_no_leaks(observer, monkeypatch):
    monkeypatch.setattr(observer.sys, "platform", "unsupported")
    with pytest.raises(observer.ProcessObservationUnavailable, match="unsupported"):
        observer.observe_owned_processes("a" * 32, 123)


def test_unreadable_known_session_members_are_explicit(observer, monkeypatch):
    root, child = 123, 456
    owner = "a" * 32
    monkeypatch.setattr(observer, "_process_pids", lambda: (child,))

    def identity(pid):
        if pid == child:
            raise PermissionError("metadata unavailable")
        return observer.ProcessIdentity(root, root, 1, os.getuid(), False)

    monkeypatch.setattr(observer, "process_identity", identity)
    monkeypatch.setattr(observer, "process_owner_tokens", lambda pid: (owner,))
    original = observer.os.getsid
    monkeypatch.setattr(observer.os, "getsid", lambda pid: root if pid == child else original(pid))
    found = observer.observe_owned_processes(owner, root)
    assert found.owned == ()
    assert found.unavailable == (child,)


def test_scratch_registration_binds_exact_directory_and_does_not_authorize_shared_paths(
    observer, tmp_path
):
    owner = uuid.uuid4().hex
    scratch = observer.create_scratch_root(owner, parent=tmp_path)
    try:
        assert scratch.path.parent == tmp_path.resolve()
        assert scratch.path.stat().st_mode & 0o777 == 0o700
        encoded = observer.encode_scratch_root(scratch)
        assert observer.decode_scratch_root(encoded, owner) == scratch
        assert observer.scratch_contains(scratch, scratch.path / "child")
        assert not observer.scratch_contains(scratch, tmp_path)
        assert not observer.scratch_contains(scratch, Path(str(scratch.path) + "-foreign"))
        with pytest.raises(observer.ProcessObservationUnavailable):
            observer.decode_scratch_root(encoded, uuid.uuid4().hex)
        scratch.path.chmod(0o755)
        with pytest.raises(observer.ProcessObservationUnavailable):
            observer.decode_scratch_root(encoded, owner)
    finally:
        scratch.path.chmod(0o700)
        observer.remove_scratch_root(scratch)


@pytest.mark.parametrize("observer", ["engine", "template"], indirect=True)
def test_native_scratch_ownership_excludes_similarly_named_foreign_directory(observer, tmp_path):
    owner = uuid.uuid4().hex
    scratch = observer.create_scratch_root(owner, parent=tmp_path)
    nested = scratch.path / "nested"
    nested.mkdir()
    foreign = tmp_path / (scratch.path.name + "-foreign")
    foreign.mkdir()
    processes = []

    def spawn(cwd, environment):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=cwd,
            env=environment,
            start_new_session=True,
        )
        processes.append(process)
        return process

    try:
        root = spawn(tmp_path, dict(os.environ, SIGNETUM_PROCESS_OWNERS=json.dumps([owner])))
        child = spawn(nested, {})
        unrelated = spawn(foreign, {})
        assert observer.process_cwd(child.pid) == nested
        scan = observer.observe_owned_processes(owner, root.pid, scratch)
        assert [(item.identity.pid, item.ownership) for item in scan.owned] == [
            (child.pid, "scratch-cwd")
        ]
        settled = observer.settle_owned_processes(owner, root.pid, scratch)
        assert settled.leaked == (child.pid,)
        assert settled.remaining == ()
        assert settled.unavailable == ()
        assert root.poll() is None and unrelated.poll() is None
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        observer.remove_scratch_root(scratch)


def test_replaced_scratch_is_refused_without_deleting_its_replacement(observer, tmp_path):
    scratch = observer.create_scratch_root(uuid.uuid4().hex, parent=tmp_path)
    retained = tmp_path / "retained-original"
    scratch.path.rename(retained)
    scratch.path.mkdir(mode=0o700)
    sentinel = scratch.path / "unrelated-data"
    sentinel.touch()
    try:
        with pytest.raises(observer.ProcessObservationUnavailable):
            observer.remove_scratch_root(scratch)
        assert sentinel.exists()
        with pytest.raises(observer.ProcessObservationUnavailable):
            observer.observe_owned_processes(scratch.owner, os.getpid(), scratch)
    finally:
        sentinel.unlink()
        scratch.path.rmdir()
        retained.rename(scratch.path)
        observer.remove_scratch_root(scratch)


def test_reused_session_root_cannot_authorize_an_unrelated_process(observer, monkeypatch):
    owner = "a" * 32
    root, child = 123, 456
    original = observer.ProcessIdentity(root, root, 100, os.getuid(), False)
    replacement = observer.ProcessIdentity(root, root, 200, os.getuid(), False)
    candidate = observer.ProcessIdentity(child, root, 201, os.getuid(), False)
    roots = iter((original, replacement))
    monkeypatch.setattr(observer, "_process_pids", lambda: (child,))
    monkeypatch.setattr(
        observer, "process_identity", lambda pid: next(roots) if pid == root else candidate
    )
    monkeypatch.setattr(
        observer, "process_owner_tokens", lambda pid: (owner,) if pid == root else ()
    )
    assert observer.observe_owned_processes(owner, root).owned == ()
