"""Record the opening engine and enforce the batch engine source."""

from dataclasses import asdict
from pathlib import Path

from signetum import runtime_identity
from signetum.operations import AdmissionError
from signetum.workspaces import BatchEngine, branch_name, read_record, state_root

INSTALLED_SKILL = (
    "invoke the installed Skill launcher: sh ~/.claude/skills/signetum/scripts/signetum"
)


def opening_engine(repository: Path) -> BatchEngine:
    source = runtime_identity.engine_source(repository)
    if source == "checkout":
        raise AdmissionError(
            "batch-open refuses an engine from a foreign checkout",
            expected=INSTALLED_SKILL,
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
    expected = _required_source(pin, source)
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
        **({"expected": expected} if expected else {}),
    }


def _required_source(pin: BatchEngine | None, source: str) -> str | None:
    if pin is not None and pin.source != source:
        if pin.source == "repository":
            return "run the repository engine from the batch worktree"
        return INSTALLED_SKILL
    return INSTALLED_SKILL if source == "checkout" else None


def require_batch_engine(repository: Path) -> None:
    record = read_record(state_root(repository), branch_name(repository))
    source = runtime_identity.engine_source(repository)
    expected = _required_source(record.engine, source)
    if expected:
        raise AdmissionError(f"batch operations refuse engine source {source}", expected=expected)
