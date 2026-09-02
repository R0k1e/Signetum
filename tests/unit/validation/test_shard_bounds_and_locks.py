"""A shard cannot run unbounded, and one operator mutates a batch at a time."""

import subprocess
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

    for gate in manifest.validation.gates:
        unprepared = [
            name
            for name in gate.shards
            if name != environment and environment not in requires[name]
        ]
        assert unprepared == [], f"{gate.name} runs {unprepared} without {environment}"
