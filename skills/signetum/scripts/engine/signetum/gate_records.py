"""Machine-local gate diagnostics and exact batch verification; no failure debt."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from signetum.git import git_output, run_git
from signetum.manifest import load_manifest
from signetum.operations import AdmissionError
from signetum.validation.execution import ValidationExecutionError
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


def failed_tip(repository: Path, branch: str, gate: str | None) -> str | None:
    """The tip a remembered failure of ``gate`` observed; unreadable means none."""
    try:
        document = json.loads(failure_path(repository, branch).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict) or (gate is not None and document.get("gate") != gate):
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


def remember_failure(
    repository: Path,
    branch: str,
    *,
    gate: str,
    base: str,
    tip: str,
    error: ValidationExecutionError,
) -> None:
    """Persist only this run's diagnostics, ignoring all historical ledgers."""
    failed = list(dict.fromkeys((*error.failed_nodes, *error.recovered_nodes)))
    unreached = [node for node in error.unreached_nodes if node not in failed]
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
            "unreached": [{"shard": shard, "node_id": node} for shard, node in unreached],
            "failed_shards": [failure.document() for failure in error.failed_shards],
        },
    )


def forget_failures(repository: Path, branch: str) -> None:
    failure_path(repository, branch).unlink(missing_ok=True)


def _pending_path(repository: Path, branch: str) -> Path:
    return _location(repository, "pending-admissions", branch)


def pending_admissions(repository: Path, branch: str) -> tuple[Path, ...]:
    """Members a conflicted admission still owes this batch, in requested order."""
    path = _pending_path(repository, branch)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()
    except (OSError, ValueError) as error:
        raise AdmissionError(
            f"pending admission record is unreadable: {path}",
            expected="inspect that machine-local record; it lists members still to admit",
        ) from error
    members = document.get("members") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or document.get("batch") != branch
        or not isinstance(members, list)
        or not all(isinstance(item, str) and item for item in members)
    ):
        raise AdmissionError(
            f"pending admission record is invalid: {path}",
            expected="inspect that machine-local record; it lists members still to admit",
        )
    return tuple(Path(item) for item in members)


def record_pending_admissions(repository: Path, branch: str, members: tuple[Path, ...]) -> None:
    if not members:
        clear_pending_admissions(repository, branch)
        return
    _write(
        _pending_path(repository, branch),
        {"schema_version": 1, "batch": branch, "members": [str(item) for item in members]},
    )


def clear_pending_admissions(repository: Path, branch: str) -> None:
    _pending_path(repository, branch).unlink(missing_ok=True)
