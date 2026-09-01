"""RepoSeal-owned execution deviations and human review projections."""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 -- fixed Git invocation, never a shell
import sys
import tomllib
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from shutil import which
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")]


class DeviationError(ValueError):
    """The requested deviation operation violates the ledger contract."""


class FrozenModel(BaseModel):
    """Strict immutable execution-state boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class DeviationClass(StrEnum):
    IMPLEMENTATION_CLARIFICATION = "implementation_clarification"
    SAFE_SUPPORTING_CHANGE = "safe_supporting_change"
    DECISION_REQUIRED = "decision_required"


class ResolutionKind(StrEnum):
    RESOLVED_IN_SPECIFICATION = "resolved_in_specification"
    RESOLVED_IN_DECISION = "resolved_in_decision"
    RESOLVED_IN_ARCHITECTURE = "resolved_in_architecture"
    RESOLVED_IN_TESTS = "resolved_in_tests"
    NO_AUTHORITY_CHANGE = "no_authority_change"
    DEFERRED = "deferred"
    REJECTED = "rejected"


class Discovered(FrozenModel):
    event: Literal["discovered"] = "discovered"
    id: Identifier
    change_id: Identifier
    member: str = Field(min_length=1)
    at: datetime
    summary: str = Field(min_length=1)
    classification: DeviationClass
    original_commitment: str = Field(min_length=1)
    action: str = Field(min_length=1)
    impact: str = Field(min_length=1)


class Resolved(FrozenModel):
    event: Literal["resolved"] = "resolved"
    id: Identifier
    change_id: Identifier
    member: str = Field(min_length=1)
    at: datetime
    resolution: ResolutionKind
    targets: tuple[str, ...] = ()
    reason: str = Field(min_length=1)
    implemented: bool


DeviationEvent = Annotated[Discovered | Resolved, Field(discriminator="event")]
EVENT_ADAPTER = TypeAdapter(DeviationEvent)


class DeviationState(FrozenModel):
    discovered: Discovered
    resolution: Resolved | None = None


def git_common_dir(repository: Path) -> Path:
    """Resolve the one common Git directory shared by linked worktrees."""
    git = which("git")
    if git is None:
        raise DeviationError("Git executable is unavailable")
    completed = subprocess.run(  # nosec B603  # noqa: S603
        (
            git,
            "-C",
            str(repository.resolve()),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise DeviationError(completed.stderr.strip() or "Git common directory is unavailable")
    common = Path(completed.stdout.strip())
    if not common.is_absolute():
        raise DeviationError("Git returned a non-absolute common directory")
    return common.resolve()


def ledger_path(repository: Path, change_id: str) -> Path:
    """Return the deterministic per-change ledger path."""
    _validate_identity(change_id)
    return git_common_dir(repository) / "reposeal" / "changes" / change_id / "deviations.jsonl"


def append_event(repository: Path, event: DeviationEvent) -> Path:
    """Validate and append exactly one complete event with O_APPEND semantics."""
    target = ledger_path(repository, event.change_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = EVENT_ADAPTER.dump_json(event) + b"\n"
    if len(encoded) > 65_536:
        raise DeviationError("deviation event exceeds the atomic record bound")
    descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        written = os.write(descriptor, encoded)
        if written != len(encoded):
            raise DeviationError("deviation event append was incomplete")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return target


def read_states(repository: Path, change_id: str) -> tuple[DeviationState, ...]:
    """Reduce the strict append-only ledger into one current state per deviation."""
    target = ledger_path(repository, change_id)
    if not target.exists():
        return ()
    discovered: dict[str, Discovered] = {}
    resolved: dict[str, Resolved] = {}
    try:
        lines = target.read_bytes().splitlines()
    except OSError as error:
        raise DeviationError(f"deviation ledger is unreadable: {error}") from error
    for number, line in enumerate(lines, start=1):
        try:
            event = EVENT_ADAPTER.validate_json(line)
        except ValidationError as error:
            raise DeviationError(f"invalid deviation event at line {number}: {error}") from error
        if event.change_id != change_id:
            raise DeviationError(f"deviation event at line {number} belongs to another change")
        if isinstance(event, Discovered):
            if event.id in discovered:
                raise DeviationError(f"duplicate deviation discovery: {event.id}")
            if event.id in resolved:
                raise DeviationError(f"deviation resolved before discovery: {event.id}")
            discovered[event.id] = event
        else:
            if event.id not in discovered:
                raise DeviationError(f"deviation resolved before discovery: {event.id}")
            if event.id in resolved:
                raise DeviationError(f"duplicate deviation resolution: {event.id}")
            if event.member != discovered[event.id].member:
                raise DeviationError(f"deviation member changed during resolution: {event.id}")
            resolved[event.id] = event
    return tuple(
        DeviationState(discovered=item, resolution=resolved.get(item.id))
        for item in sorted(discovered.values(), key=lambda value: value.id)
    )


def reconciliation_summary(repository: Path, change_ids: tuple[str, ...]) -> dict[str, object]:
    """Validate terminal resolutions and return delivery-review source data."""
    changes: list[dict[str, object]] = []
    pending: list[str] = []
    deviation_count = 0
    for change_id in sorted(set(change_ids)):
        states = read_states(repository, change_id)
        rows: list[dict[str, object]] = []
        for state in states:
            deviation_count += 1
            if state.resolution is None:
                pending.append(f"{change_id}/{state.discovered.id}")
            else:
                _validate_resolution(repository, state)
            rows.append(
                {
                    "id": state.discovered.id,
                    "summary": state.discovered.summary,
                    "classification": state.discovered.classification.value,
                    "member": state.discovered.member,
                    "resolution": (
                        state.resolution.resolution.value
                        if state.resolution is not None
                        else "pending"
                    ),
                    "targets": list(state.resolution.targets) if state.resolution else [],
                    "reason": state.resolution.reason if state.resolution else "",
                }
            )
        changes.append({"change_id": change_id, "deviations": rows})
    if pending:
        raise DeviationError(f"unresolved deviations: {', '.join(pending)}")
    return {"changes": changes, "deviation_count": deviation_count}


def approval_view(repository: Path, change_id: str) -> dict[str, object]:
    """Project the tracked Review and Specification into a concise approval payload."""
    change = repository.resolve() / "changes" / change_id
    try:
        review = tomllib.loads((change / "review.toml").read_text(encoding="utf-8"))["review"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise DeviationError(f"approved Review is unavailable: {error}") from error
    clauses = review.get("clauses")
    if not isinstance(clauses, list):
        raise DeviationError("Review clauses are unavailable")
    commitments = [item.get("statement") for item in clauses if isinstance(item, dict)]
    if not commitments or not all(isinstance(item, str) and item for item in commitments):
        raise DeviationError("Review commitments are invalid")
    specs = sorted((change / "specs").glob("*.toml"))
    evidence: list[str] = []
    for path in specs:
        try:
            specification = tomllib.loads(path.read_text(encoding="utf-8"))["specification"]
        except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
            raise DeviationError(f"Specification is unavailable: {error}") from error
        if (
            specification.get("status") != "approved"
            or specification.get("implementation_authorized") is not True
        ):
            raise DeviationError(f"Specification is not implementation-authorized: {path}")
        raw_acceptance = specification.get("acceptance", ())
        if isinstance(raw_acceptance, list):
            evidence.extend(str(item) for item in raw_acceptance)
    return {
        "schema_version": 1,
        "status": "approval",
        "change_id": change_id,
        "outcomes": commitments,
        "acceptance": evidence,
        "autonomy": {
            "continue": ["implementation_clarification", "safe_supporting_change"],
            "freeze_affected_work": ["decision_required"],
        },
    }


def _validate_resolution(repository: Path, state: DeviationState) -> None:
    resolution = state.resolution
    if resolution is None:
        raise DeviationError(f"unresolved deviation: {state.discovered.id}")
    target_required = resolution.resolution in {
        ResolutionKind.RESOLVED_IN_SPECIFICATION,
        ResolutionKind.RESOLVED_IN_DECISION,
        ResolutionKind.RESOLVED_IN_ARCHITECTURE,
        ResolutionKind.RESOLVED_IN_TESTS,
        ResolutionKind.DEFERRED,
    }
    if target_required and not resolution.targets:
        raise DeviationError(f"resolution requires an authority target: {resolution.id}")
    for raw_target in resolution.targets:
        target = PurePosixPath(raw_target)
        if target.is_absolute() or ".." in target.parts or str(target) in {"", "."}:
            raise DeviationError(f"resolution target is not repository-relative: {raw_target}")
        path = repository.resolve() / target
        if not path.exists():
            raise DeviationError(f"resolution target is absent: {raw_target}")
        if resolution.resolution == ResolutionKind.RESOLVED_IN_DECISION:
            if not raw_target.startswith("docs/decisions/"):
                raise DeviationError(
                    f"decision resolution target is outside decisions: {raw_target}"
                )
            content = path.read_text(encoding="utf-8")
            if "Status: Accepted" not in content:
                raise DeviationError(f"decision resolution target is not accepted: {raw_target}")
    if (
        state.discovered.classification == DeviationClass.DECISION_REQUIRED
        and resolution.implemented
    ):
        approved = resolution.resolution in {
            ResolutionKind.RESOLVED_IN_SPECIFICATION,
            ResolutionKind.RESOLVED_IN_DECISION,
        }
        if not approved:
            raise DeviationError(
                f"decision-required deviation was implemented without authority: {resolution.id}"
            )


def _validate_identity(value: str) -> None:
    try:
        TypeAdapter(Identifier).validate_python(value, strict=True)
    except ValidationError as error:
        raise DeviationError(f"invalid change identity: {value}") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    commands = parser.add_subparsers(dest="command", required=True)
    approval = commands.add_parser("approval")
    approval.add_argument("--change", required=True)
    record = commands.add_parser("record")
    record.add_argument("--change", required=True)
    record.add_argument("--id", required=True)
    record.add_argument("--member", required=True)
    record.add_argument(
        "--class", dest="classification", choices=tuple(DeviationClass), required=True
    )
    record.add_argument("--summary", required=True)
    record.add_argument("--commitment", required=True)
    record.add_argument("--action", required=True)
    record.add_argument("--impact", required=True)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--change", required=True)
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--member", required=True)
    resolve.add_argument("--resolution", choices=tuple(ResolutionKind), required=True)
    resolve.add_argument("--target", action="append", default=[])
    resolve.add_argument("--reason", required=True)
    resolve.add_argument("--implemented", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("--change", required=True, action="append")
    return parser


def main(arguments: list[str] | None = None) -> int:
    parsed = _parser().parse_args(arguments)
    repository = parsed.repository.resolve()
    try:
        if parsed.command == "approval":
            result = approval_view(repository, parsed.change)
        elif parsed.command == "record":
            event = Discovered(
                id=parsed.id,
                change_id=parsed.change,
                member=parsed.member,
                at=datetime.now(UTC),
                summary=parsed.summary,
                classification=DeviationClass(parsed.classification),
                original_commitment=parsed.commitment,
                action=parsed.action,
                impact=parsed.impact,
            )
            path = append_event(repository, event)
            result = {
                "schema_version": 1,
                "status": "recorded",
                "id": event.id,
                "ledger": str(path),
            }
        elif parsed.command == "resolve":
            event = Resolved(
                id=parsed.id,
                change_id=parsed.change,
                member=parsed.member,
                at=datetime.now(UTC),
                resolution=ResolutionKind(parsed.resolution),
                targets=tuple(parsed.target),
                reason=parsed.reason,
                implemented=parsed.implemented,
            )
            states = {
                state.discovered.id: state for state in read_states(repository, parsed.change)
            }
            if parsed.id not in states:
                raise DeviationError(f"deviation is absent: {parsed.id}")
            path = append_event(repository, event)
            result = {
                "schema_version": 1,
                "status": "resolved",
                "id": event.id,
                "ledger": str(path),
            }
        else:
            result = {
                "schema_version": 1,
                "status": "reconciled",
                **reconciliation_summary(repository, tuple(parsed.change)),
            }
    except (DeviationError, OSError) as error:
        print(
            json.dumps(
                {"schema_version": 1, "status": "refused", "reason": str(error)}, sort_keys=True
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
