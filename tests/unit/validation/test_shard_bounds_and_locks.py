"""A shard cannot run unbounded, and one operator mutates a batch at a time."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

import signetum.lifecycle as lifecycle
from signetum.validation import (
    GateDeclaration,
    GraphContribution,
    ValidationGraphError,
    ValidationShard,
    resolve_validation_graph,
)
from signetum.validation.execution import ValidationInfrastructureError
from signetum.validation.process import run_command
from signetum.validation.repository import RepositoryValidationAdapter


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "seed.txt").write_text("seed\n", encoding="utf-8")
    for command in (
        ("git", "init", "-b", "main"),
        ("git", "config", "user.name", "Signetum test"),
        ("git", "config", "user.email", "signetum@example.invalid"),
        ("git", "add", "."),
        ("git", "commit", "-m", "seed"),
    ):
        subprocess.run(command, cwd=repository, check=True, capture_output=True)
    return repository


def test_a_shard_declares_a_positive_time_bound() -> None:
    assert ValidationShard("core:one", ("true",)).timeout_seconds > 0

    with pytest.raises(ValidationGraphError, match="time bound must be positive"):
        ValidationShard("core:two", ("true",), (), "tree", (), 0)


def test_a_shard_which_does_not_return_is_reported_as_such(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    shard = ValidationShard("core:hang", ("sleep", "30"), (), "tree", (), 1)

    execution = RepositoryValidationAdapter(repository).run_shard(shard)

    assert execution.succeeded is False
    assert "did not return within 1s" in execution.diagnostic
    assert "core:hang" in execution.diagnostic


def test_missing_executable_is_infrastructure_failure(tmp_path):
    shard = ValidationShard("test:missing", (str(tmp_path / "missing-command"),))
    with pytest.raises(ValidationInfrastructureError, match="unavailable"):
        RepositoryValidationAdapter(tmp_path).run_shard(shard)


@pytest.mark.parametrize("times_out", [False, True])
def test_nested_runner_owns_group_and_returns_control_to_its_adapter(tmp_path, times_out):
    header = (
        "import os, sys, json, subprocess; from pathlib import Path; "
        "from signetum.validation.process import run_command\n"
    )
    if times_out:
        body = (
            "try:\n"
            "    run_command(Path.cwd(), [sys.executable, '-c', 'import time; time.sleep(30)'], "
            "timeout_seconds=0.2)\n"
            "except subprocess.TimeoutExpired:\n"
            "    print('handled timeout')\n"
        )
    else:
        body = (
            "child='import os; print(os.getpgrp())'\n"
            "result=run_command(Path.cwd(), [sys.executable, '-c', child], timeout_seconds=3)\n"
            "print(json.dumps([os.getpgrp(), int(result.stdout)]))\n"
        )
    result = run_command(tmp_path, (sys.executable, "-c", header + body), timeout_seconds=5)
    assert result.returncode == 0, result.stderr
    if times_out:
        assert result.stdout.strip() == "handled timeout"
    else:
        parent, child = json.loads(result.stdout)
        assert parent != child


def test_the_time_bound_is_part_of_the_graph_identity() -> None:
    def graph(bound: int) -> str:
        return resolve_validation_graph(
            (
                GraphContribution(
                    "core",
                    shards=(ValidationShard("core:one", ("true",), (), "tree", (), bound),),
                    gates=(GateDeclaration("final", ("core:one",)),),
                ),
            )
        ).digest

    assert graph(60) != graph(120)


@pytest.mark.parametrize("nested_adapter", [False, True])
def test_timeout_terminates_descendants_before_returning(tmp_path, nested_adapter):
    marker = tmp_path / "orphan-finished"
    child = (
        "import time; from pathlib import Path; time.sleep(2); "
        "Path(__import__('sys').argv[1]).touch()"
    )
    parent = (
        "import subprocess, sys; subprocess.run([sys.executable, '-c', sys.argv[1], sys.argv[2]])"
    )
    if nested_adapter:
        parent = (
            "import sys; from pathlib import Path; "
            "from signetum.validation.process import run_command; "
            "run_command(Path.cwd(), [sys.executable, '-c', sys.argv[1], sys.argv[2]], "
            "timeout_seconds=30)"
        )
    shard = ValidationShard(
        "test:children", (sys.executable, "-c", parent, child, str(marker)), timeout_seconds=1
    )
    result = RepositoryValidationAdapter(tmp_path).run_shard(shard)
    assert not result.succeeded
    time.sleep(1.5)
    assert not marker.exists(), "timed-out validation left a child running"


def test_a_batch_admits_one_operator_at_a_time(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with lifecycle._exclusive_batch(repository):
        with pytest.raises(lifecycle.AdmissionError, match="batch is held by"):
            with lifecycle._exclusive_batch(repository):
                pass

    with lifecycle._exclusive_batch(repository):
        pass


def test_the_refusal_names_the_holder(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with lifecycle._exclusive_batch(repository):
        with pytest.raises(lifecycle.AdmissionError) as failure:
            with lifecycle._exclusive_batch(repository):
                pass

    assert "pid " in str(failure.value)


def test_every_gate_shard_depends_on_the_shard_which_builds_the_environment() -> None:
    """A gate in a freshly created worktree must not rely on who created it."""
    manifest = lifecycle.load_manifest(Path(__file__).resolve().parents[3] / "signetum.toml")
    requires = {shard.name: set(shard.requires) for shard in manifest.validation.shards}
    environment = next(
        name for name, needed in requires.items() if not needed and name.endswith(":sync")
    )

    def prepared(name, seen=()):
        return name == environment or (
            name not in seen
            and any(prepared(dependency, (*seen, name)) for dependency in requires[name])
        )

    for gate in manifest.validation.gates:
        unprepared = [name for name in gate.shards if not prepared(name)]
        assert unprepared == [], f"{gate.name} runs {unprepared} without {environment}"


def test_inner_deadline_terminates_descendants_without_killing_outer_adapter(tmp_path):
    marker = tmp_path / "inner-orphan"
    child = "import time,sys; from pathlib import Path; time.sleep(2); Path(sys.argv[1]).touch()"
    parent = "import subprocess,sys; subprocess.run([sys.executable,'-c',sys.argv[1],sys.argv[2]])"
    adapter = (
        "import sys,time,subprocess; from pathlib import Path; "
        "from signetum.validation.process import run_command\n"
        "started=time.monotonic()\n"
        "try:\n"
        "    run_command(Path.cwd(), [sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]], "
        "timeout_seconds=0.5)\n"
        "except subprocess.TimeoutExpired:\n"
        "    print(time.monotonic()-started)\n"
    )
    result = run_command(
        tmp_path, (sys.executable, "-c", adapter, parent, child, str(marker)), timeout_seconds=5
    )
    assert result.returncode == 0, result.stderr
    assert float(result.stdout) < 1.5
    time.sleep(2)
    assert not marker.exists()
