# Generated from signetum.synchronization; edit the engine source and regenerate.
"""Machine-local attestation of sources verified by workspace-sync."""

import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from functools import cache
from pathlib import Path

from .git import git_output
from .workspaces import state_root


def _path(repository: Path, base: str, before: str, source: str) -> Path:
    digest = hashlib.sha256(json.dumps([base, before, source]).encode()).hexdigest()
    return state_root(repository) / "synchronization" / f"{digest}.json"


def authorize_source(repository: Path, base: str, source: str, kind: str) -> None:
    before = git_output(repository, "rev-parse", "HEAD")
    destination = _path(repository, base, before, source)
    record = {"schema_version": 1, "base": base, "before": before, "source": source, "kind": kind}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=destination.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(record, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def verified_syncs(repository: Path, base: str, tip: str) -> tuple[tuple[str, str], ...]:
    sources: list[tuple[str, str]] = []
    for merge in git_output(
        repository, "rev-list", "--first-parent", "--merges", f"{base}..{tip}"
    ).splitlines():
        parents = git_output(repository, "show", "-s", "--format=%P", merge).split()
        if len(parents) != 2:
            continue
        before, source = parents
        body = git_output(repository, "show", "-s", "--format=%B", merge)
        if re.findall(r"^Signetum-Sync:\s*(\S+)$", body, re.MULTILINE) != [source]:
            continue
        try:
            record = json.loads(_path(repository, base, before, source).read_text(encoding="utf-8"))
            if record == {
                "schema_version": 1,
                "base": base,
                "before": before,
                "source": source,
                "kind": record.get("kind"),
            } and record["kind"] in ("delivery", "batch"):
                sources.append((merge, source))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return tuple(sources)


def verified_sync_sources(repository: Path, base: str, tip: str) -> tuple[str, ...]:
    return tuple(source for _, source in verified_syncs(repository, base, tip))


def member_contribution_paths(repository: Path, base: str, tip: str) -> tuple[str, ...]:
    @cache
    def changed_between(before: str, after: str) -> frozenset[str]:
        return frozenset(
            filter(
                None,
                git_output(
                    repository,
                    "diff",
                    "--name-only",
                    "-z",
                    "--no-renames",
                    before,
                    after,
                    strip=False,
                ).split("\0"),
            )
        )

    owned: set[str] = set()
    inherited: dict[str, str] = {}
    synchronized = dict(verified_syncs(repository, base, tip))
    history = git_output(
        repository, "log", "--first-parent", "--reverse", "--format=%H%x09%P", f"{base}..{tip}"
    )
    for entry in history.splitlines():
        commit, _, raw_parents = entry.partition("\t")
        parents = raw_parents.split()
        before = parents[0] if parents else base
        touched = changed_between(before, commit)
        if source := synchronized.get(commit):
            from_source = changed_between(source, commit)
            for path in touched | changed_between(before, source) | owned:
                if path not in from_source:
                    inherited[path] = source
                    owned.discard(path)
                elif path in touched:
                    inherited[path] = source
                    owned.add(path)
                elif path in owned:
                    inherited[path] = source
            continue
        by_authority: dict[str, set[str]] = defaultdict(set)
        for path in touched:
            by_authority[inherited.get(path, base)].add(path)
        for reference, paths in by_authority.items():
            differences = changed_between(reference, commit)
            owned.difference_update(paths - differences)
            owned.update(paths & differences)
    return tuple(sorted(owned))
