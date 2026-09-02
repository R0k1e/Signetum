"""Self-contained Signetum deviation ledger and human review projections."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from shutil import which

CLASSES = {"implementation_clarification", "safe_supporting_change", "decision_required"}
RESOLUTIONS = {
    "resolved_in_specification",
    "resolved_in_decision",
    "resolved_in_architecture",
    "resolved_in_tests",
    "no_authority_change",
    "deferred",
    "rejected",
}
TARGET_REQUIRED = {
    "resolved_in_specification",
    "resolved_in_decision",
    "resolved_in_architecture",
    "resolved_in_tests",
    "deferred",
}
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class DeviationError(ValueError):
    pass


def _common(repository: Path) -> Path:
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
    return Path(completed.stdout.strip()).resolve()


def ledger_path(repository: Path, change_id: str) -> Path:
    if IDENTIFIER.fullmatch(change_id) is None:
        raise DeviationError(f"invalid change identity: {change_id}")
    return _common(repository) / "signetum" / "changes" / change_id / "deviations.jsonl"


def append_event(repository: Path, event: dict[str, object]) -> Path:
    _validate_event(event)
    target = ledger_path(repository, str(event["change_id"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > 65_536:
        raise DeviationError("deviation event exceeds the atomic record bound")
    descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        if os.write(descriptor, encoded) != len(encoded):
            raise DeviationError("deviation event append was incomplete")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return target


def read_states(repository: Path, change_id: str) -> tuple[dict[str, object], ...]:
    target = ledger_path(repository, change_id)
    if not target.exists():
        return ()
    states: dict[str, dict[str, object]] = {}
    for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
            _validate_event(event)
        except (json.JSONDecodeError, DeviationError) as error:
            raise DeviationError(f"invalid deviation event at line {number}: {error}") from error
        if event["change_id"] != change_id:
            raise DeviationError(f"deviation event at line {number} belongs to another change")
        identifier = str(event["id"])
        if event["event"] == "discovered":
            if identifier in states:
                raise DeviationError(f"duplicate deviation discovery: {identifier}")
            states[identifier] = {"discovered": event, "resolution": None}
        else:
            if identifier not in states:
                raise DeviationError(f"deviation resolved before discovery: {identifier}")
            if states[identifier]["resolution"] is not None:
                raise DeviationError(f"duplicate deviation resolution: {identifier}")
            discovered = states[identifier]["discovered"]
            if isinstance(discovered, dict) and discovered["member"] != event["member"]:
                raise DeviationError(f"deviation member changed during resolution: {identifier}")
            states[identifier]["resolution"] = event
    return tuple(states[key] for key in sorted(states))


def reconciliation_summary(repository: Path, change_ids: tuple[str, ...]) -> dict[str, object]:
    changes: list[dict[str, object]] = []
    pending: list[str] = []
    count = 0
    extra_work: list[str] = []
    unfinished_work: list[str] = []
    authority_updates: set[str] = set()
    for change_id in sorted(set(change_ids)):
        rows: list[dict[str, object]] = []
        for state in read_states(repository, change_id):
            count += 1
            discovered = state["discovered"]
            resolution = state["resolution"]
            if not isinstance(discovered, dict):
                raise DeviationError("invalid discovered state")
            if resolution is None:
                pending.append(f"{change_id}/{discovered['id']}")
                resolution_name, targets, reason = "pending", [], ""
            elif isinstance(resolution, dict):
                _validate_resolution(repository, discovered, resolution)
                resolution_name = str(resolution["resolution"])
                targets = resolution["targets"]
                reason = str(resolution["reason"])
                authority_updates.update(str(item) for item in targets)
                if resolution_name == "deferred":
                    unfinished_work.append(f"{change_id}/{discovered['id']}")
            else:
                raise DeviationError("invalid resolution state")
            rows.append(
                {
                    "id": discovered["id"],
                    "summary": discovered["summary"],
                    "classification": discovered["classification"],
                    "member": discovered["member"],
                    "resolution": resolution_name,
                    "targets": targets,
                    "reason": reason,
                }
            )
            if discovered["classification"] == "safe_supporting_change":
                extra_work.append(f"{change_id}/{discovered['id']}")
        changes.append({"change_id": change_id, "deviations": rows})
    if pending:
        raise DeviationError(f"unresolved deviations: {', '.join(pending)}")
    return {
        "changes": changes,
        "deviation_count": count,
        "extra_work": extra_work,
        "unfinished_work": unfinished_work,
        "authority_updates": sorted(authority_updates),
    }


def approval_view(repository: Path, change_id: str) -> dict[str, object]:
    change = repository.resolve() / "changes" / change_id
    try:
        review = tomllib.loads((change / "review.toml").read_text(encoding="utf-8"))["review"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise DeviationError(f"approved Review is unavailable: {error}") from error
    clauses = review.get("clauses")
    if not isinstance(clauses, list):
        raise DeviationError("Review clauses are unavailable")
    outcomes = [
        item.get("statement")
        for item in clauses
        if isinstance(item, dict) and item.get("disposition") == "covered"
    ]
    non_goals = [
        {"statement": item.get("statement"), "reason": item.get("reason")}
        for item in clauses
        if isinstance(item, dict) and item.get("disposition") == "out_of_scope"
    ]
    deferred = [
        item.get("statement")
        for item in clauses
        if isinstance(item, dict) and item.get("disposition") == "deferred"
    ]
    if not outcomes or not all(isinstance(item, str) and item for item in outcomes):
        raise DeviationError("Review commitments are invalid")
    evidence: list[str] = []
    for path in sorted((change / "specs").glob("*.toml")):
        specification = tomllib.loads(path.read_text(encoding="utf-8"))["specification"]
        if (
            specification.get("status") != "approved"
            or specification.get("implementation_authorized") is not True
        ):
            raise DeviationError(f"Specification is not implementation-authorized: {path}")
        acceptance = specification.get("acceptance", [])
        if isinstance(acceptance, list):
            evidence.extend(str(item) for item in acceptance)
    return {
        "schema_version": 1,
        "status": "approval",
        "change_id": change_id,
        "outcomes": outcomes,
        "non_goals": non_goals,
        "deferred": deferred,
        "acceptance": evidence,
        "autonomy": {
            "continue": ["implementation_clarification", "safe_supporting_change"],
            "freeze_affected_work": ["decision_required"],
        },
    }


def _validate_event(event: object) -> None:
    if not isinstance(event, dict):
        raise DeviationError("event must be an object")
    required = {"event", "id", "change_id", "member", "at"}
    if not required.issubset(event):
        raise DeviationError("event fields are incomplete")
    if any(not isinstance(event[key], str) or not event[key] for key in required):
        raise DeviationError("event identity fields must be non-empty strings")
    if (
        IDENTIFIER.fullmatch(str(event["id"])) is None
        or IDENTIFIER.fullmatch(str(event["change_id"])) is None
    ):
        raise DeviationError("event identity is invalid")
    if event["event"] == "discovered":
        fields = {"summary", "classification", "original_commitment", "action", "impact"}
        if set(event) != required | fields or event["classification"] not in CLASSES:
            raise DeviationError("discovery fields are invalid")
    elif event["event"] == "resolved":
        fields = {"resolution", "targets", "reason", "implemented"}
        if set(event) != required | fields or event["resolution"] not in RESOLUTIONS:
            raise DeviationError("resolution fields are invalid")
        if not isinstance(event["targets"], list) or not isinstance(event["implemented"], bool):
            raise DeviationError("resolution values are invalid")
    else:
        raise DeviationError("event kind is invalid")


def _validate_resolution(
    repository: Path, discovered: dict[str, object], resolved: dict[str, object]
) -> None:
    resolution = str(resolved["resolution"])
    targets = resolved["targets"]
    if not isinstance(targets, list):
        raise DeviationError("resolution targets are invalid")
    if resolution in TARGET_REQUIRED and not targets:
        raise DeviationError(f"resolution requires an authority target: {resolved['id']}")
    for raw in targets:
        target = PurePosixPath(str(raw))
        if target.is_absolute() or ".." in target.parts or str(target) in {"", "."}:
            raise DeviationError(f"resolution target is not repository-relative: {raw}")
        path = repository.resolve() / target
        if not path.exists():
            raise DeviationError(f"resolution target is absent: {raw}")
        if resolution == "resolved_in_decision":
            content = path.read_text(encoding="utf-8")
            if not str(raw).startswith("docs/decisions/") or "Status: Accepted" not in content:
                raise DeviationError(f"decision resolution target is not accepted: {raw}")
    if discovered["classification"] == "decision_required" and resolved["implemented"] is True:
        if resolution not in {"resolved_in_specification", "resolved_in_decision"}:
            raise DeviationError(
                f"decision-required deviation was implemented without authority: {resolved['id']}"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    commands = parser.add_subparsers(dest="command", required=True)
    approval = commands.add_parser("approval")
    approval.add_argument("--change", required=True)
    record = commands.add_parser("record")
    for name in ("change", "id", "member", "summary", "commitment", "action", "impact"):
        record.add_argument(f"--{name}", required=True)
    record.add_argument("--class", dest="classification", choices=sorted(CLASSES), required=True)
    resolve = commands.add_parser("resolve")
    for name in ("change", "id", "member", "reason"):
        resolve.add_argument(f"--{name}", required=True)
    resolve.add_argument("--resolution", choices=sorted(RESOLUTIONS), required=True)
    resolve.add_argument("--target", action="append", default=[])
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
            event = {
                "event": "discovered",
                "id": parsed.id,
                "change_id": parsed.change,
                "member": parsed.member,
                "at": datetime.now(UTC).isoformat(),
                "summary": parsed.summary,
                "classification": parsed.classification,
                "original_commitment": parsed.commitment,
                "action": parsed.action,
                "impact": parsed.impact,
            }
            result = {
                "schema_version": 1,
                "status": "recorded",
                "ledger": str(append_event(repository, event)),
            }
        elif parsed.command == "resolve":
            states: dict[str, dict[str, object]] = {}
            for item in read_states(repository, parsed.change):
                discovered = item.get("discovered")
                if not isinstance(discovered, dict) or not isinstance(discovered.get("id"), str):
                    raise DeviationError("invalid discovered state")
                states[discovered["id"]] = item
            if parsed.id not in states:
                raise DeviationError(f"deviation is absent: {parsed.id}")
            event = {
                "event": "resolved",
                "id": parsed.id,
                "change_id": parsed.change,
                "member": parsed.member,
                "at": datetime.now(UTC).isoformat(),
                "resolution": parsed.resolution,
                "targets": parsed.target,
                "reason": parsed.reason,
                "implemented": parsed.implemented,
            }
            result = {
                "schema_version": 1,
                "status": "resolved",
                "ledger": str(append_event(repository, event)),
            }
        else:
            result = {
                "schema_version": 1,
                "status": "reconciled",
                **reconciliation_summary(repository, tuple(parsed.change)),
            }
    except (DeviationError, OSError, KeyError, tomllib.TOMLDecodeError) as error:
        print(
            json.dumps(
                {"schema_version": 1, "status": "refused", "reason": str(error)}, sort_keys=True
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
