"""Machine-local attestation of sources verified by workspace-sync."""

import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from signetum.git import git_output
from signetum.workspaces import state_root


def _path(repository: Path, base: str, before: str, source: str) -> Path:
    digest = hashlib.sha256(json.dumps([base, before, source]).encode()).hexdigest()
    return state_root(repository) / "synchronization" / f"{digest}.json"


def _recognition_path(repository: Path, merge: str) -> Path:
    return state_root(repository) / "synchronization" / "recognized" / f"{merge}.json"


def authorize_source(repository: Path, base: str, source: str, kind: str) -> None:
    before = git_output(repository, "rev-parse", "HEAD")
    record = {"schema_version": 1, "base": base, "before": before, "source": source, "kind": kind}
    _write(_path(repository, base, before, source), record)


def _write(destination: Path, record: Mapping[str, object]) -> None:
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


SYNC_KINDS = ("delivery", "batch", "parent")


def _verified_syncs(repository: Path, base: str, tip: str) -> tuple[tuple[str, str, str], ...]:
    """Recorded workspace-sync merges, newest first, with the kind of source each merged."""

    sources: list[tuple[str, str, str]] = []
    for merge in git_output(
        repository, "rev-list", "--first-parent", "--merges", f"{base}..{tip}"
    ).splitlines():
        parents = git_output(repository, "show", "-s", "--format=%P", merge).split()
        if len(parents) != 2:
            continue
        before, source = parents
        if not _trailer(repository, merge, source) and not _recognized(
            repository, merge, base, source
        ):
            continue
        if (kind := _sync_kind(repository, base, before, source)) is not None:
            sources.append((merge, source, kind))
    return tuple(sources)


def _trailer(repository: Path, merge: str, source: str) -> bool:
    body = git_output(repository, "show", "-s", "--format=%B", merge)
    return re.findall(r"^Signetum-Sync:\s*(\S+)$", body, re.MULTILINE) == [source]


def _read(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _sync_kind(repository: Path, base: str, before: str, source: str) -> str | None:
    """The kind of the sync record workspace-sync wrote for exactly these commits."""

    record = _read(_path(repository, base, before, source))
    if not isinstance(record, dict) or record.get("kind") not in SYNC_KINDS:
        return None
    expected = {"schema_version": 1, "base": base, "before": before, "source": source}
    return record["kind"] if record == {**expected, "kind": record["kind"]} else None


def _recognized(repository: Path, merge: str, base: str, source: str) -> bool:
    expected = {"schema_version": 1, "merge": merge, "base": base, "source": source}
    return _read(_recognition_path(repository, merge)) == expected


def recognize_sync(repository: Path, base: str, source: str) -> str | None:
    """Bind the recorded sync merge of ``source`` whose trailer was lost.

    Only a first-parent merge of exactly ``source`` with the sync record
    workspace-sync wrote is recognized; a manual merge stays unverified.
    """

    for merge in git_output(
        repository, "rev-list", "--first-parent", "--merges", f"{base}..HEAD"
    ).splitlines():
        parents = git_output(repository, "show", "-s", "--format=%P", merge).split()
        if len(parents) != 2 or parents[1] != source:
            continue
        if _trailer(repository, merge, source) or _recognized(repository, merge, base, source):
            return None
        if _sync_kind(repository, base, parents[0], source) is None:
            return None
        record = {"schema_version": 1, "merge": merge, "base": base, "source": source}
        _write(_recognition_path(repository, merge), record)
        return merge
    return None


def verified_syncs(repository: Path, base: str, tip: str) -> tuple[tuple[str, str], ...]:
    return tuple((merge, source) for merge, source, _ in _verified_syncs(repository, base, tip))


def incorporated_parent_tip(repository: Path, base: str, tip: str) -> str:
    """The parent tip a stacked member holds: its latest parent sync, otherwise its base."""

    return next(
        (source for _, source, kind in _verified_syncs(repository, base, tip) if kind == "parent"),
        base,
    )


def verified_sync_sources(repository: Path, base: str, tip: str) -> tuple[str, ...]:
    return tuple(source for _, source in verified_syncs(repository, base, tip))


def unrecorded_merges(repository: Path, base: str, tip: str) -> tuple[str, ...]:
    """First-parent merges which workspace-sync did not record, newest first."""

    verified = {merge for merge, _ in verified_syncs(repository, base, tip)}
    merges = git_output(
        repository, "rev-list", "--first-parent", "--merges", f"{base}..{tip}"
    ).splitlines()
    return tuple(merge for merge in merges if merge not in verified)


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
