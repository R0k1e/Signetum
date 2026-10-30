# Generated from signetum.change.paths; edit the engine source and regenerate.
"""One declared root for current change records and retained history."""

from .manifest import RepositoryManifest


def changes_root(manifest: RepositoryManifest) -> str:
    return manifest.repository.changes
