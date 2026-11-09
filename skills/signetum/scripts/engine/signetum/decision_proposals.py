"""Affected Proposed decisions read from immutable Git snapshots."""

import re
from pathlib import Path

from signetum.git import git_output
from signetum.manifest import RepositoryManifest
from signetum.source_authority import committed_blob


def proposal_paths(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str
) -> tuple[str, ...]:
    """Leave unchanged historical proposals untouched, as final does."""
    changed = git_output(
        repository,
        "diff",
        "--name-only",
        "--diff-filter=ACMRT",
        "-z",
        base,
        tip,
        "--",
        manifest.repository.decisions,
    )
    paths = []
    for path in changed.split("\0"):
        if not path or not Path(path).match("*ADP-*.md"):
            continue
        blob = committed_blob(repository, tip, path)
        if blob is not None and re.search(r"^Status:\s*Proposed\s*$", blob[1][:512], re.MULTILINE):
            paths.append(path)
    return tuple(paths)
