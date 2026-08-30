"""Check-only public command line interface."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from development_foundation.manifest import ManifestError, load_manifest
from development_foundation.profiles import ProfileError, resolve_profiles
from development_foundation.release import ReleaseError, preflight
from development_foundation.status.models import EvidenceSnapshot
from development_foundation.traceability.boundary import TraceabilityManifest
from development_foundation.traceability.cli import query

app = typer.Typer(add_completion=False, help="Validate development-foundation contracts.")
check_app = typer.Typer(add_completion=False, help="Run read-only repository checks.")
app.add_typer(check_app, name="check")
release_app = typer.Typer(add_completion=False, help="Verify immutable release candidates.")
app.add_typer(release_app, name="release")


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


@check_app.command("manifest")
def check_manifest(
    manifest: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    """Validate a repository manifest through the composable check namespace."""
    validate(manifest)


@check_app.command("traceability")
def check_traceability(
    repository: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    changes_root: Annotated[str, typer.Option()] = "changes",
    decision_root: Annotated[list[str] | None, typer.Option()] = None,
    legacy_root: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Validate Review, Specification, Plan, and decision relations."""
    exit_code = query(
        repository.resolve(),
        TraceabilityManifest(
            schema_version=1,
            changes_root=changes_root,
            decision_roots=tuple(decision_root or ("docs/decisions",)),
            legacy_roots=tuple(legacy_root or ()),
        ),
        EvidenceSnapshot(),
        sys.stdout,
        sys.stderr,
    )
    if exit_code:
        raise typer.Exit(code=int(exit_code))


@release_app.command("preflight")
def release_preflight(
    source: Annotated[str, typer.Option()],
    repository: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
) -> None:
    """Verify that an exact source has matching final evidence."""
    try:
        metadata = preflight(repository.resolve(), source)
    except (OSError, ReleaseError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "invalid"}, sort_keys=True))
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            {"status": "valid", "release": metadata.model_dump(mode="json")},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    app()
