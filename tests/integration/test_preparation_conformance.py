"""Preparation guards and configured execution agree at both frontends."""

import importlib
import json
import sys

import pytest
from test_lifecycle_conformance import _template_lifecycle

from signetum import maintenance, workspace_operations
from signetum.git import git_output
from signetum.workspaces import state_root


@pytest.fixture(params=["engine", "template"])
def preparation(request, repository):
    root, state = repository
    runtime = workspace_operations if request.param == "engine" else _template_lifecycle()
    return runtime, root, state


def commit(root, path, content):
    (root / path).write_text(content)
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "configure preparation scenario")


def change_command(root, command):
    path = root / "signetum.toml"
    text = path.read_text()
    manifest = workspace_operations.load_manifest(path)
    previous = next(s.command for s in manifest.validation.shards if s.name == "test:prepare")
    commit(root, "signetum.toml", text.replace(json.dumps(list(previous)), json.dumps(command)))


def test_preparation_executes_only_its_gate_without_changing_source_or_issuing_evidence(
    preparation,
):
    runtime, root, state = preparation
    tip = git_output(root, "rev-parse", "HEAD")
    result = runtime.worktree_prepare(root)
    assert result == {"status": "prepared", "worktree": str(root), "executed": ["test:prepare"]}
    assert (state / "attempts").read_text() == "1"
    assert git_output(root, "rev-parse", "HEAD") == tip
    assert git_output(root, "status", "--porcelain") == ""
    assert not (state_root(root) / "validation").exists()


def test_preparation_failure_keeps_source_and_can_retry(preparation):
    runtime, root, state = preparation
    tip = git_output(root, "rev-parse", "HEAD")
    (state / "fail").touch()
    with pytest.raises(runtime.InfrastructureError):
        runtime.worktree_prepare(root)
    assert git_output(root, "rev-parse", "HEAD") == tip
    (state / "fail").unlink()
    assert runtime.worktree_prepare(root)["status"] == "prepared"
    assert (state / "attempts").read_text() == "2"
    assert not (state_root(root) / "validation").exists()


def test_preparation_requires_its_declared_gate(preparation):
    runtime, root, state = preparation
    path = root / "signetum.toml"
    commit(
        root,
        "signetum.toml",
        path.read_text().replace(
            '[[validation.gates]]\nname = "prepare"\nshards = ["test:prepare"]\n', ""
        ),
    )
    with pytest.raises(runtime.AdmissionError, match="declare a prepare gate"):
        runtime.worktree_prepare(root)
    assert not (state / "attempts").exists()


@pytest.mark.parametrize("merge", [False, True])
def test_preparation_refuses_unstaged_or_untracked_work(preparation, merge):
    runtime, root, state = preparation
    (root / "untracked.txt").write_text("preserve me")
    with pytest.raises(runtime.AdmissionError):
        runtime.worktree_prepare(root, allow_merge=merge)
    assert (root / "untracked.txt").read_text() == "preserve me"
    assert not (state / "attempts").exists()


@pytest.mark.parametrize("stage", [False, True])
def test_preparation_cannot_rewrite_staged_resolution(preparation, stage, capsys):
    runtime, root, _ = preparation
    script = (
        "from pathlib import Path; import subprocess; "
        "Path('seed.txt').write_text('tool edit'); print('preparation output')"
    )
    if stage:
        script += "; subprocess.run(['git','add','seed.txt'],check=True)"
    change_command(root, [sys.executable, "-c", script])
    (root / "seed.txt").write_text("staged resolution")
    git_output(root, "add", "seed.txt")
    tip = git_output(root, "rev-parse", "HEAD")
    with pytest.raises(
        importlib.import_module(
            "signetum.operations"
            if runtime is workspace_operations
            else "_signetum_runtime.operations"
        ).OperationFailed,
        match="changed the staged merge",
    ):
        runtime.worktree_prepare(root, allow_merge=True)
    assert git_output(root, "rev-parse", "HEAD") == tip
    assert (root / "seed.txt").read_text() == "tool edit"
    assert "preparation output" in capsys.readouterr().err


def test_preparation_refuses_a_command_that_advances_head(preparation):
    runtime, root, _ = preparation
    change_command(root, ["git", "commit", "--allow-empty", "-m", "unexpected tool commit"])
    tip = git_output(root, "rev-parse", "HEAD")
    with pytest.raises(
        importlib.import_module(
            "signetum.operations"
            if runtime is workspace_operations
            else "_signetum_runtime.operations"
        ).OperationFailed,
        match="changed the committed source",
    ):
        runtime.worktree_prepare(root)
    assert git_output(root, "rev-parse", "HEAD") != tip


def test_public_preparation_uses_explicit_worktree_and_one_result(
    preparation, monkeypatch, capsys, tmp_path
):
    runtime, root, state = preparation
    frontend = (
        maintenance
        if runtime is workspace_operations
        else importlib.import_module("_signetum_runtime.maintenance")
    )
    monkeypatch.chdir(tmp_path)
    assert frontend.main(["worktree-prepare", str(root)]) == 0
    output = capsys.readouterr()
    assert len(output.out.splitlines()) == 1
    result = json.loads(output.out)
    assert result["operation"] == "worktree-prepare"
    assert result["status"] == "passed"
    assert result["outcome"] == "prepared"
    assert result["worktree"] == str(root)
    assert result["executed"] == ["test:prepare"]
    assert (state / "attempts").read_text() == "1"
    assert not (state_root(root) / "validation").exists()
