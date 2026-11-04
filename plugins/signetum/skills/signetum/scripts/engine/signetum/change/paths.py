"""One declared root for current change records and retained history."""

from signetum.manifest import RepositoryManifest


def changes_root(manifest: RepositoryManifest) -> str:
    return manifest.repository.changes
