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


@pytest.fixture(params=["engine", "template"])
def observer(request, monkeypatch):
    if request.param == "engine":
        return process_observation
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[3] / "template/.agents/repo-dev/runtime")
    )
    return importlib.import_module("_signetum_runtime.process_observation")


def test_native_observation_finds_only_owned_detached_processes(observer):
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
