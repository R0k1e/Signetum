"""Check-only public command line interface."""

import json
from pathlib import Path
from typing import Annotated

import typer

from development_foundation.manifest import ManifestError, load_manifest
from development_foundation.profiles import ProfileError, resolve_profiles

app = typer.Typer(add_completion=False, help="Validate development-foundation contracts.")


@app.callback()
def main() -> None:
    """Run a check-only foundation command."""


@app.command()
def validate(manifest: Annotated[Path, typer.Option(exists=True, dir_okay=False)]) -> None:
    """Validate one repository manifest and emit exactly one JSON result."""

    try:
        loaded = load_manifest(manifest)
        profiles = resolve_profiles(loaded.profiles)
    except (ManifestError, ProfileError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "invalid"}, sort_keys=True))
        raise typer.Exit(code=2) from error

    typer.echo(
        json.dumps(
            {
                "foundation": loaded.foundation.version,
                "manifest_schema": loaded.schema_version,
                "profiles": [profile.identity for profile in profiles],
                "status": "valid",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    app()
