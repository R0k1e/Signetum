"""Delivery survives remote rejection and interruption without losing local state."""

import importlib
import json
import subprocess
import sys
from pathlib import Path
from shutil import which

import pytest
from test_batch_admission import MANIFEST
from test_lifecycle_conformance import _template_lifecycle

from signetum import lifecycle
from signetum.execution_review import execution_review_inputs
from signetum.manifest import load_manifest
from signetum.operations import OperationFailed
from signetum.workspaces import WorkspaceRecord, write_record


@pytest.fixture(autouse=True)
def delivery_frontend(request, monkeypatch):
    if getattr(request, "param", "engine") == "template":
        runtime = _template_lifecycle()
        errors = importlib.import_module("_signetum_runtime.operations")
        monkeypatch.setattr(sys.modules[__name__], "lifecycle", runtime)
        monkeypatch.setattr(sys.modules[__name__], "OperationFailed", errors.OperationFailed)


def git(repository: Path, *arguments: str) -> str:
    executable = which("git")
    if executable is None:
        raise RuntimeError("Git is required for delivery scenarios")
    return subprocess.run(  # nosec B603
        (executable, "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init", "-b", "main")
    git(target, "config", "user.name", "Delivery Test")
    git(target, "config", "user.email", "delivery@example.invalid")
    (target / "content").write_text("base")
    (target / "signetum.toml").write_text(MANIFEST)
    policy = target / ".agents/repo-dev/repo.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("delivery:\n  branch: main\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "base")
    base = git(target, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    git(target, "remote", "add", "origin", str(remote))
    git(target, "push", "origin", "main")
    source = tmp_path / "batch"
    git(target, "worktree", "add", "-b", "batch/test", str(source))
    (source / "content").write_text("delivered")
    git(source, "commit", "-am", "implement")
    tip = git(source, "rev-parse", "HEAD")
    write_record(
        lifecycle._state_root(source),
        WorkspaceRecord(schema_version=1, branch="batch/test", base=base, kind="batch"),
    )
    receipts = lifecycle._receipt_root(source)
    (receipts / "final-test.json").write_text(
        json.dumps(
            {
                "source": tip,
                "base": base,
                "valid": True,
                "delivery_review": {
                    "inputs": execution_review_inputs(
                        source, load_manifest(source / "signetum.toml"), base, tip, receipts
                    )
                },
            }
        )
    )
    (receipts / "final-zzz.json").write_text(
        json.dumps({"source": base, "base": base, "valid": True})
    )
    monkeypatch.setattr(lifecycle, "_attested_base", lambda *args: base)
    monkeypatch.setattr(lifecycle, "_delivery_provenance", lambda *args: ([], []))
    monkeypatch.setattr(lifecycle, "_cleanup_delivered_worktrees", lambda *args: ([], []))
    return source, target, remote, base, tip


@pytest.mark.parametrize("delivery_frontend", ["engine", "template"], indirect=True)
def test_rejected_push_keeps_target_at_base(tmp_path, monkeypatch):
    source, target, remote, base, tip = delivery(tmp_path, monkeypatch)
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)

    with pytest.raises(OperationFailed):
        lifecycle.batch_deliver(source, target, base, tip)

    assert git(target, "rev-parse", "HEAD") == base
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == base
    hook.unlink()
    result = lifecycle.batch_deliver(source, target, base, tip)
    landed = git(target, "rev-parse", "HEAD")
    assert result["remote"] == landed
    assert git(target, "show", "-s", "--format=%P", landed).split() == [base, tip]


@pytest.mark.parametrize("delivery_frontend", ["engine", "template"], indirect=True)
def test_published_delivery_resumes_local_move(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    original = lifecycle._git

    def interrupt(repository, *arguments, **kwargs):
        if repository == target and arguments[:2] == ("merge", "--ff-only"):
            raise lifecycle.AdmissionError("simulated interruption after publication")
        return original(repository, *arguments, **kwargs)

    monkeypatch.setattr(lifecycle, "_git", interrupt)
    with pytest.raises(lifecycle.AdmissionError, match="simulated interruption"):
        lifecycle.batch_deliver(source, target, base, tip)
    published = git(target, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert published != base
    assert git(target, "rev-parse", "HEAD") == base

    monkeypatch.setattr(lifecycle, "_git", original)
    result = lifecycle.batch_deliver(source, target, base, tip)
    assert result["remote"] == published
    assert git(target, "rev-parse", "HEAD") == published


@pytest.mark.parametrize("delivery_frontend", ["engine", "template"], indirect=True)
def test_delivery_retries_cleanup_after_target_moved(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)

    def interrupted_cleanup(*args):
        raise lifecycle.AdmissionError("simulated cleanup interruption")

    monkeypatch.setattr(lifecycle, "_cleanup_delivered_worktrees", interrupted_cleanup)
    with pytest.raises(lifecycle.AdmissionError, match="cleanup interruption"):
        lifecycle.batch_deliver(source, target, base, tip)
    published = git(target, "rev-parse", "HEAD")
    monkeypatch.setattr(lifecycle, "_cleanup_delivered_worktrees", lambda *args: ([], []))
    result = lifecycle.batch_deliver(source, target, base, tip)
    assert result["remote"] == published


@pytest.mark.parametrize("delivery_frontend", ["engine", "template"], indirect=True)
def test_unrelated_remote_change_is_refused_without_local_move(tmp_path, monkeypatch):
    source, target, remote, base, tip = delivery(tmp_path, monkeypatch)
    git(source, "push", "origin", f"{tip}:refs/heads/other")
    git(remote, "update-ref", "refs/heads/main", tip)
    with pytest.raises(lifecycle.AdmissionError, match="remote delivery branch"):
        lifecycle.batch_deliver(source, target, base, tip)
    assert git(target, "rev-parse", "HEAD") == base


def test_delivery_refuses_a_target_outside_the_validated_policy(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    git(target, "switch", "-c", "unintended")
    git(target, "push", "origin", "unintended")
    with pytest.raises(lifecycle.AdmissionError, match="repository-declared delivery branch"):
        lifecycle.batch_deliver(source, target, base, tip)
    assert git(target, "rev-parse", "HEAD") == base
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == base
    assert git(target, "ls-remote", "origin", "refs/heads/unintended").split()[0] == base


@pytest.mark.parametrize("delivery_frontend", ["engine", "template"], indirect=True)
def test_unconfirmed_publication_keeps_local_target_and_can_resume(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    observe = lifecycle._remote_branch_tip
    calls = 0

    def unavailable_confirmation(repository, branch):
        nonlocal calls
        calls += 1
        return base if calls == 2 else observe(repository, branch)

    monkeypatch.setattr(lifecycle, "_remote_branch_tip", unavailable_confirmation)
    with pytest.raises(lifecycle.AdmissionError, match="remote delivery confirmation"):
        lifecycle.batch_deliver(source, target, base, tip)
    published = git(target, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert published != base
    assert git(target, "rev-parse", "HEAD") == base
    monkeypatch.setattr(lifecycle, "_remote_branch_tip", observe)
    assert lifecycle.batch_deliver(source, target, base, tip)["remote"] == published
    assert git(target, "rev-parse", "HEAD") == published


@pytest.mark.parametrize("delivery_frontend", ["engine", "template"], indirect=True)
def test_matching_parents_with_different_tree_cannot_resume_delivery(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    other = git(
        source,
        "commit-tree",
        f"{base}^{{tree}}",
        "-p",
        base,
        "-p",
        tip,
        "-m",
        "unrelated tree with matching parents",
    )
    git(source, "push", "origin", f"{other}:refs/heads/main")
    with pytest.raises(lifecycle.AdmissionError, match="remote delivery branch"):
        lifecycle.batch_deliver(source, target, base, tip)
    assert git(target, "rev-parse", "HEAD") == base
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == other
