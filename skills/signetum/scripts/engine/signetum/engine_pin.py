"""Batch engine authority captured at opening, checked before batch work."""

from dataclasses import asdict
from pathlib import Path

from signetum import runtime_identity
from signetum.operations import AdmissionError
from signetum.workspaces import BatchEngine, branch_name, read_record, state_root

REMEDY = "finish this batch with that engine, or open a new batch for the same ready members"


def opening_engine(repository: Path) -> BatchEngine:
    source = runtime_identity.engine_source(repository)
    if source == "checkout":
        raise AdmissionError(
            "batch-open refuses an engine from a foreign checkout",
            expected=(
                "invoke the installed Skill: "
                "sh ~/.claude/skills/signetum/scripts/signetum batch-open"
            ),
        )
    observed = runtime_identity.identity()
    return BatchEngine(
        version=str(observed["version"]),
        implementation=str(observed["implementation"]),
        source=source,
    )


def engine_status(repository: Path) -> dict[str, object]:
    record = read_record(state_root(repository), branch_name(repository))
    if record.kind != "batch" or record.engine is None:
        return {"status": "unpinned"}
    pin = record.engine
    source = runtime_identity.engine_source(repository)
    observed = runtime_identity.identity()
    matches = source == pin.source and (
        source == "repository"
        or (observed["version"], observed["implementation"]) == (pin.version, pin.implementation)
    )
    return {
        "status": "matched" if matches else "mismatch",
        "pinned": asdict(pin),
        "running": {
            "version": observed["version"],
            "implementation": observed["implementation"],
            "source": source,
        },
        **({"expected": REMEDY} if not matches else {}),
    }


def require_batch_engine(repository: Path) -> None:
    status = engine_status(repository)
    if status["status"] == "mismatch":
        pin = status["pinned"]
        raise AdmissionError(f"batch engine mismatch: pinned {pin}", expected=REMEDY)
