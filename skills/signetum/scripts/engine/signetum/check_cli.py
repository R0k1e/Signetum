"""Read-only project checks registered by the common command table."""

import json
from pathlib import Path
from typing import Annotated

import typer

from signetum.manifest import ManifestError, load_manifest
from signetum.profiles import ProfileError, resolve_profiles
from signetum.traceability.cli import main as traceability_main


def _manifest(manifest: Annotated[Path, typer.Option(exists=True, dir_okay=False)]) -> None:
    """Validate one repository manifest and emit exactly one JSON result."""

    try:
        loaded = load_manifest(manifest)
        profiles = resolve_profiles(
            loaded.profiles.enabled,
            replacements=loaded.profiles.replacements,
        )
    except (ManifestError, ProfileError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "invalid"}, sort_keys=True))
        raise typer.Exit(code=2) from error

    typer.echo(
        json.dumps(
            {
                "protocol": loaded.signetum.protocol,
                "manifest_schema": loaded.schema_version,
                "profiles": [profile.identity for profile in profiles],
                "status": "valid",
            },
            sort_keys=True,
        )
    )


def check_manifest(
    manifest: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    """Validate a repository manifest through the composable check namespace."""
    _manifest(manifest)


def check_traceability(
    repository: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    changes_root: Annotated[str | None, typer.Option()] = None,
    decision_root: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Validate current change records and retained decision relations."""
    arguments = ["--repository", str(repository.resolve())]
    if changes_root is not None:
        arguments.extend(("--changes-root", changes_root))
    for root in decision_root or ():
        arguments.extend(("--decision-root", root))
    exit_code = traceability_main(arguments)
    if exit_code:
        raise typer.Exit(code=int(exit_code))
