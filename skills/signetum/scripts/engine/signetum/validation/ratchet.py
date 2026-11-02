"""Compare diagnostic multisets against a verified synchronization source."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess  # nosec B404
import tarfile
import tempfile
import time
from collections import Counter
from pathlib import Path

from signetum.git import git_output, repository_path, run_git
from signetum.synchronization import verified_sync_sources
from signetum.validation import ValidationShard
from signetum.validation.diagnostic_protocol import diagnostic_multiset
from signetum.validation.execution import ShardExecution, ValidationInfrastructureError
from signetum.validation.process import run_command
from signetum.workspaces import state_root
from signetum.worktrunk import declared_argv, declared_environment


def _trusted_paths(repository: Path) -> str:
    """Trust the tree this measurement checks, without recording that trust.

    A materialized baseline is a new repository, so Mise does not reuse the
    member worktree's trust. An operator-supplied path list is kept.
    """

    path = str(repository)
    current = os.environ.get("MISE_TRUSTED_CONFIG_PATHS", "")
    parts = [item for item in current.split(":") if item and item != path]
    parts.append(path)
    return ":".join(parts)


def _measure(repository: Path, command: tuple[str, ...], deadline: float, workers: int) -> str:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValidationInfrastructureError("ratchet diagnostic deadline exhausted")
    try:
        result = run_command(
            repository,
            declared_argv(tuple(command)),
            timeout_seconds=remaining,
            environment=declared_environment(
                extra={
                    "SIGNETUM_VALIDATION_WORKERS": str(workers),
                    "MISE_TRUSTED_CONFIG_PATHS": _trusted_paths(repository),
                }
            ),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValidationInfrastructureError(f"diagnostic command unavailable: {error}") from error
    if result.returncode:
        raise ValidationInfrastructureError(
            f"diagnostic command did not execute: {result.stdout}{result.stderr}"
        )
    diagnostic_multiset(result.stdout)
    return result.stdout


def _materialize(repository: Path, base: str, destination: Path) -> None:
    archive = destination.parent / "source.tar"
    git_output(repository, "archive", "--format=tar", f"--output={archive}", base)
    destination.mkdir()
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination, filter="data")
    # An isolated index/HEAD makes Git-aware checks see the archived inventory.
    # This repository has no registered worktree and cannot mutate the source.
    git_output(destination, "init", "--quiet")
    objects = repository_path(repository, "rev-parse", "--git-path", "objects")
    (destination / ".git/objects/info/alternates").write_text(f"{objects}\n", encoding="utf-8")
    git_output(destination, "read-tree", base)
    git_output(destination, "update-ref", "refs/heads/snapshot", base)
    git_output(destination, "symbolic-ref", "HEAD", "refs/heads/snapshot")
    if run_git(destination, "update-index", "--refresh").returncode:
        raise ValidationInfrastructureError("archived baseline differs from the committed tree")


def ratchet_baseline(repository: Path, recorded_base: str, tip: str) -> str:
    sources = verified_sync_sources(repository, recorded_base, tip)
    return sources[0] if sources else recorded_base


def run_ratchet(
    repository: Path,
    shard: ValidationShard,
    recorded_base: str,
    tools: tuple[tuple[str, str], ...],
    *,
    workers: int = 0,
) -> ShardExecution:
    deadline = time.monotonic() + shard.timeout_seconds
    tip = git_output(repository, "rev-parse", "HEAD")
    baseline = ratchet_baseline(repository, recorded_base, tip)
    driver = hashlib.sha256(
        Path(__file__).read_bytes()
        + Path(__file__).with_name("diagnostic_protocol.py").read_bytes()
        + Path(__file__).with_name("process.py").read_bytes()
    ).hexdigest()
    identity = {
        "schema_version": 1,
        "baseline": baseline,
        "command": list(shard.ratchet_command),
        "tools": list(tools),
        "driver": driver,
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = state_root(repository) / "validation/ratchets" / f"{key}.json"
    current = diagnostic_multiset(_measure(repository, shard.ratchet_command, deadline, workers))
    previous: Counter[tuple[str, str, str]] = Counter()
    unavailable = None
    cached = False
    try:
        record = json.loads(cache.read_text(encoding="utf-8"))
        # JSON normalizes tuple tool identities to arrays.
        if record["identity"] == json.loads(json.dumps(identity)):
            previous = diagnostic_multiset(record["document"])
            cached = True
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if not cached:
        try:
            with tempfile.TemporaryDirectory(prefix="signetum-ratchet-") as scratch:
                root = Path(scratch) / "source"
                _materialize(repository, baseline, root)
                document = _measure(root, shard.ratchet_command, deadline, workers)
                previous = diagnostic_multiset(document)
            cache.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=cache.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump({"identity": identity, "document": document}, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                temporary.replace(cache)
            finally:
                temporary.unlink(missing_ok=True)
        except ValidationInfrastructureError as error:
            unavailable = str(error)
    added = current - previous
    details = {
        "baseline": baseline,
        "current_count": current.total(),
        "baseline_count": previous.total(),
        "new_count": added.total(),
        "baseline_cached": cached,
        "baseline_unavailable": unavailable,
    }
    if added:
        findings = [
            {"file": path, "rule": rule, "message": message, "count": count}
            for (path, rule, message), count in sorted(added.items())
        ]
        return ShardExecution(
            False,
            f"{shard.name}: baseline={baseline} unavailable={unavailable}; "
            f"new diagnostics: {json.dumps(findings, sort_keys=True)}",
            details={"ratchet": details},
        )
    return ShardExecution(True, details={"ratchet": details})
