"""Declared change roots shared by committed-source and lifecycle readers."""

from pathlib import PurePosixPath

from signetum.manifest import ManifestError, RepositoryManifest


def changes_root(manifest: RepositoryManifest) -> str:
    """Resolve the package root from the declared per-change specification glob."""

    parts = PurePosixPath(manifest.repository.specifications).parts
    try:
        position = parts.index("*")
    except ValueError as error:
        raise ManifestError("specification authority must declare per-change packages") from error
    if position == 0:
        raise ManifestError("specification authority has no repository-owned change root")
    return PurePosixPath(*parts[:position]).as_posix()
