# Generated from signetum.test_diagnostic; edit the engine source and regenerate.
"""Run an explicitly declared test shard without readiness or workspace registration."""

import argparse
from dataclasses import replace
from pathlib import Path

from .execution import ValidationExecutionError, require_original_success
from .manifest import load_manifest
from .operation_cli import OperationParser, run_operation
from .operations import AdmissionError
from .repository import RepositoryValidationAdapter
from .workspaces import state_root


def run_test_diagnostic(
    repository: Path, shard_name: str, arguments: tuple[str, ...]
) -> dict[str, object]:
    manifest = load_manifest(repository / "signetum.toml")
    shard = next((item for item in manifest.validation.shards if item.name == shard_name), None)
    if shard is None:
        raise AdmissionError("diagnostic requires an explicitly declared shard")
    if shard.ratchet_command:
        raise AdmissionError("test diagnostics cannot replace a ratchet measurement")
    selected = replace(shard, command=(*shard.command, *arguments))
    execution = RepositoryValidationAdapter(repository).run_shard(selected)
    if not execution.succeeded:
        raise ValidationExecutionError(execution.diagnostic or f"{shard.name} failed")
    require_original_success([{**item, "shard": shard.name} for item in execution.recovered])
    return {"status": "diagnostic", "shard": shard.name, "details": execution.details}


def main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--shard", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    repository = Path.cwd()

    def invoke() -> dict[str, object]:
        nonlocal repository
        options = parser.parse_args(arguments)
        repository = options.repository.resolve()
        supplied = options.arguments
        if supplied[:1] == ["--"]:
            supplied = supplied[1:]
        return run_test_diagnostic(repository, options.shard, tuple(supplied))

    return run_operation(repository, "test", invoke, state_root=lambda _: state_root(repository))
