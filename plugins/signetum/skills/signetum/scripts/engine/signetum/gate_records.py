"""Machine-local gate memory beside synchronization records.

A failed gate leaves a failure receipt for its workspace. Before the next gate in
that workspace runs checks, each remembered node must be selected again, and then
pass, or be named with its root cause by an observation in a change journal the
workspace changed. A passing batch gate records the tip it verified, so the next
admission selects only the commits added after it.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from signetum.development_store import snapshot
from signetum.git import git_output, run_git
from signetum.manifest import load_manifest
from signetum.operations import AdmissionError
from signetum.validation.execution import NodeIdentity, ValidationExecutionError
from signetum.workspaces import state_root


def _location(repository: Path, directory: str, branch: str) -> Path:
    return state_root(repository) / directory / f"{quote(branch, safe='')}.json"


def failure_path(repository: Path, branch: str) -> Path:
    return _location(repository, "failures", branch)


def _verified_path(repository: Path, branch: str) -> Path:
    return _location(repository, "batch-verified", branch)


def _write(destination: Path, document: dict[str, object]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=destination.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(document, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def verified_batch_tip(repository: Path, branch: str, base: str) -> str:
    """Return the last batch tip whose gate passed, or the batch base."""
    path = _verified_path(repository, branch)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return base
    except (OSError, ValueError) as error:
        raise AdmissionError(
            f"batch verification record is unreadable: {path}",
            expected="inspect or remove that machine-local record and rerun the operation",
        ) from error
    verified = document.get("verified") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or document.get("branch") != branch
        or not isinstance(verified, str)
    ):
        raise AdmissionError(
            f"batch verification record is invalid: {path}",
            expected="inspect or remove that machine-local record and rerun the operation",
        )
    descent = run_git(repository, "merge-base", "--is-ancestor", verified, "HEAD")
    # A tip outside this batch's history proves nothing about the current one.
    # After synchronization advances the base, a tip verified before it still
    # sits in the batch history without descending from the new base.
    behind = verified != base and (
        run_git(repository, "merge-base", "--is-ancestor", verified, base).returncode == 0
    )
    return verified if descent.returncode == 0 and not behind else base


def record_verified_batch(repository: Path, branch: str, tip: str) -> None:
    _write(
        _verified_path(repository, branch), {"schema_version": 1, "branch": branch, "verified": tip}
    )


def _node(item: object) -> NodeIdentity:
    if (
        not isinstance(item, dict)
        or set(item) != {"shard", "node_id"}
        or not all(isinstance(value, str) and value for value in item.values())
    ):
        raise ValueError("invalid remembered node")
    return item["shard"], item["node_id"]


def remembered_failures(repository: Path, branch: str) -> tuple[NodeIdentity, ...]:
    path = failure_path(repository, branch)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError("unsupported failure receipt")
        if document.get("workspace") != branch or not isinstance(document.get("failed"), list):
            raise ValueError("failure receipt names another workspace")
        return tuple(_node(item) for item in document["failed"])
    except FileNotFoundError:
        return ()
    except (OSError, ValueError) as error:
        raise AdmissionError(
            f"failure receipt is unreadable: {path}: {error}",
            expected="inspect that machine-local receipt; it records failures still owed",
        ) from error


def failed_tip(repository: Path, branch: str, gate: str) -> str | None:
    """The tip a remembered failure of ``gate`` observed; unreadable means none."""
    try:
        document = json.loads(failure_path(repository, branch).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict) or document.get("gate") != gate:
        return None
    tip = document.get("tip")
    return tip if isinstance(tip, str) else None


def changed_changes(repository: Path, base: str) -> tuple[str, ...]:
    """Change identities whose records or journals the workspace changed since its base."""
    root = load_manifest(repository / "signetum.toml").repository.changes
    changed = git_output(repository, "diff", "--name-only", "-z", "--no-renames", base, "--", root)
    identities = {
        PurePosixPath(path).relative_to(root).parts[0]
        for path in changed.split("\0")
        if path and len(PurePosixPath(path).relative_to(root).parts) > 1
    }
    return tuple(sorted(identities))


def _documented(repository: Path, changes: Collection[str]) -> frozenset[str]:
    if not changes:
        return frozenset()
    try:
        observations = snapshot(repository).observations
    except ValueError as error:
        raise AdmissionError(f"change journals are unavailable: {error}") from error
    return frozenset(
        evidence
        for item in observations
        if item.change_id in changes
        for evidence in item.observation.evidence
    )


def require_accounted(
    repository: Path,
    branch: str,
    base: str,
    selected: Collection[str],
    *,
    defer_unselected: bool = False,
) -> dict[str, frozenset[str]]:
    """Refuse before checks unless every remembered node is documented or selected.

    A recorded root cause releases its node whatever the shard selection, since
    one shard may hold every test. Returns the undocumented nodes by shard; the
    selected ones must pass in this run. A light batch gate defers unselected
    nodes to final instead of refusing; ``settle_failures`` keeps them owed.
    """
    remembered = remembered_failures(repository, branch)
    if not remembered:
        return {}
    try:
        documented = _documented(repository, changed_changes(repository, base))
    except AdmissionError:
        # An open merge's journal may not yet verify from HEAD. Reselected
        # nodes can still prove themselves by passing; a dropped one cannot.
        if any(shard not in selected for shard, _ in remembered):
            raise
        documented = frozenset()
    owed = [node for node in remembered if node[1] not in documented]
    missing = sorted({node_id for shard, node_id in owed if shard not in selected})
    if missing and not defer_unselected:
        raise AdmissionError(
            "previously failed nodes are neither selected by this gate nor named with their "
            "root cause in a change journal of this workspace: " + ", ".join(missing),
            expected=(
                "select them again, or record each root cause with change record --id <id> "
                "--requirement <REQ> --summary <failure> --reason <root cause> --evidence "
                "<node-id>, commit it and rerun"
            ),
        )
    required: dict[str, set[str]] = {}
    for shard, node_id in owed:
        required.setdefault(shard, set()).add(node_id)
    return {shard: frozenset(nodes) for shard, nodes in required.items()}


def remember_failure(
    repository: Path,
    branch: str,
    *,
    gate: str,
    base: str,
    tip: str,
    error: ValidationExecutionError,
    owed: dict[str, frozenset[str]],
) -> None:
    """Persist what a failed gate observed, keeping owed nodes it did not prove."""
    failed = list(error.failed_nodes)
    for shard, nodes in sorted(owed.items()):
        if shard in error.passed_shards:
            continue
        failed.extend((shard, node) for node in sorted(nodes) if (shard, node) not in failed)
    _write(
        failure_path(repository, branch),
        {
            "schema_version": 1,
            "workspace": branch,
            "worktree": str(repository),
            "gate": gate,
            "changes": list(changed_changes(repository, base)),
            "base": base,
            "tip": tip,
            "recorded_at": datetime.now(UTC).isoformat(),
            "failed": [{"shard": shard, "node_id": node} for shard, node in failed],
            "recovered": [
                {"shard": shard, "node_id": node} for shard, node in error.recovered_nodes
            ],
        },
    )


def forget_failures(repository: Path, branch: str) -> None:
    failure_path(repository, branch).unlink(missing_ok=True)


def settle_failures(
    repository: Path, branch: str, owed: dict[str, frozenset[str]], passed: Collection[str]
) -> None:
    """After a passing gate, keep only owed nodes whose shards it did not run."""
    path = failure_path(repository, branch)
    remaining = [
        {"shard": shard, "node_id": node}
        for shard, nodes in sorted(owed.items())
        if shard not in passed
        for node in sorted(nodes)
    ]
    if not remaining:
        path.unlink(missing_ok=True)
        return
    document = json.loads(path.read_text(encoding="utf-8"))
    _write(path, {**document, "failed": remaining, "recovered": []})
