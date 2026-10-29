# Generated from signetum.profiles.existing_runner; edit the engine source and regenerate.
"""Opt-in application runner bindings with no installation or execution effects."""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from .contract_values import FrozenContract
from .manifest import ValidationCommands
from .serialization import Constraints, contract_mapping, dataclass_from_mapping, load_json
from .validation import GateDeclaration, ToolDeclaration, ValidationShard

Language = Literal["python", "node", "rust"]


@dataclass(frozen=True, kw_only=True)
class ExistingRunnerRequest(FrozenContract):
    language: Language
    command: Annotated[tuple[str, ...], Constraints(min_length=1)]
    tools: Annotated[tuple[ToolDeclaration, ...], Constraints(min_length=1)]
    timeout_seconds: Annotated[int, Constraints(minimum=1)] = 1800


@dataclass(frozen=True, kw_only=True)
class ExistingRunnerValidation(FrozenContract):
    identity: str
    validation: ValidationCommands


def existing_runner_validation(request: ExistingRunnerRequest) -> ExistingRunnerValidation:
    if len({tool.name for tool in request.tools}) != len(request.tools):
        raise ValueError("existing runner tool identities must be unique")
    identity = f"{request.language}-existing@1"
    name = f"profile:{identity}:test"
    return ExistingRunnerValidation(
        identity=identity,
        validation=ValidationCommands(
            tools=request.tools,
            shards=(
                ValidationShard(name, request.command, timeout_seconds=request.timeout_seconds),
            ),
            gates=(GateDeclaration("member", (name,)), GateDeclaration("final", (name,))),
            member_required=(name,),
        ),
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parsed = parser.parse_args(arguments)
    try:
        request = dataclass_from_mapping(
            ExistingRunnerRequest,
            load_json(parsed.request.read_text(encoding="utf-8")),
            use_defaults=True,
        )
        binding = existing_runner_validation(request)
    except (OSError, ValueError) as error:
        print(json.dumps({"schema_version": 1, "status": "invalid", "reason": str(error)}))
        return 2
    validation = contract_mapping(binding.validation)
    # These legacy input fields cannot authorize recovered success and are not
    # proposed as new configuration by an existing-runner adapter.
    for retired in ("recovery_window", "recovery_threshold"):
        validation.pop(retired)
    print(
        json.dumps(
            {
                "schema_version": 1,
                "status": "proposal",
                "fragment": {
                    "profiles": {"enabled": [binding.identity]},
                    "validation": validation,
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
