"""Run declared checks without readiness or workspace registration."""

import argparse
from dataclasses import replace
from pathlib import Path

from signetum.manifest import load_manifest
from signetum.operation_cli import OperationParser, run_operation
from signetum.operations import AdmissionError
from signetum.validation.execution import ValidationExecutionError, require_original_success
from signetum.validation.repository import (
    RepositoryValidationAdapter,
    configured_validation,
    run_diagnostic_gate,
)
from signetum.workspaces import state_root


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
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--shard")
    selection.add_argument("--gate")
    parser.add_argument("--exact-source", action="store_true")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    repository = Path.cwd()

    def invoke() -> dict[str, object]:
        nonlocal repository
        options = parser.parse_args(arguments)
        repository = options.repository.resolve()
        supplied = options.arguments
        if supplied[:1] == ["--"]:
            supplied = supplied[1:]
        if options.gate:
            if supplied:
                raise AdmissionError("gate diagnostics do not accept native arguments")
            graph, inputs = configured_validation(load_manifest(repository / "signetum.toml"))
            details = run_diagnostic_gate(
                repository, graph, options.gate, inputs=inputs, exact_source=options.exact_source
            )
            return {"status": "diagnostic", "gate": options.gate, "details": details}
        if options.exact_source:
            raise AdmissionError("exact-source validation requires a gate")
        return run_test_diagnostic(repository, options.shard, tuple(supplied))

    return run_operation(repository, "test", invoke, state_root=lambda _: state_root(repository))
