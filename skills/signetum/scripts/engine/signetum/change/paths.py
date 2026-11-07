"""One declared root for current change records and retained history."""

from pathlib import PurePosixPath

from signetum.manifest import RepositoryManifest


def changes_root(manifest: RepositoryManifest) -> str:
    return manifest.repository.changes


def is_record_path(path: str, root: str) -> bool:
    """A path inside one change directory: its record, journal or other history."""
    prefix = PurePosixPath(root).parts
    parts = PurePosixPath(path).parts
    return parts[: len(prefix)] == prefix and len(parts) > len(prefix) + 1
