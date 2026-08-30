"""Check-only public command line interface."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from reposeal.lifecycle import main as lifecycle_main
from reposeal.manifest import ManifestError, load_manifest
from reposeal.product_surface import validate_product_surface
from reposeal.profiles import ProfileError, resolve_profiles
from reposeal.release import ReleaseError, preflight
from reposeal.status.models import EvidenceSnapshot
from reposeal.template import render_template, validate_template
from reposeal.traceability.boundary import GitInventoryProvider, TraceabilityManifest
from reposeal.traceability.cli import query

app = typer.Typer(add_completion=False, help="Validate RepoSeal repository contracts.")
check_app = typer.Typer(add_completion=False, help="Run read-only repository checks.")
app.add_typer(check_app, name="check")
release_app = typer.Typer(add_completion=False, help="Verify immutable release candidates.")
app.add_typer(release_app, name="release")
template_app = typer.Typer(add_completion=False, help="Check or render the public Template.")
app.add_typer(template_app, name="template")


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    add_help_option=False,
)
def lifecycle(ctx: typer.Context) -> None:
    """Run one of the eight explicit repository lifecycle operations."""
    raise typer.Exit(code=lifecycle_main(list(ctx.args)))


@template_app.command("check")
def template_check(
    source: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("template"),
) -> None:
    """Validate the exact clone-ready Template inventory."""
    report = validate_template(source)
    typer.echo(
        json.dumps({"files": report.files, "problems": report.problems, "valid": report.valid})
    )
    if not report.valid:
        raise typer.Exit(code=3)


@template_app.command("render")
def template_render(
    source: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    destination: Annotated[Path, typer.Option()],
) -> None:
    """Render a checked Template into a new empty destination."""
    try:
        report = render_template(source, destination)
    except ValueError as error:
        typer.echo(json.dumps({"error": str(error), "valid": False}, sort_keys=True))
        raise typer.Exit(code=3) from error
    typer.echo(json.dumps({"files": report.files, "valid": True}, sort_keys=True))


@app.callback()
def main() -> None:
    """Run RepoSeal repository-development commands."""


@app.command()
def validate(manifest: Annotated[Path, typer.Option(exists=True, dir_okay=False)]) -> None:
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
                "reposeal": loaded.reposeal.version,
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


@check_app.command("product-surface")
def check_product_surface(
    repository: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
) -> None:
    """Validate required product assets and repository-relative Markdown links."""
    resolved = repository.resolve()
    try:
        inventory = GitInventoryProvider().read(resolved)
        report = validate_product_surface(resolved, inventory)
    except (OSError, ValueError) as error:
        typer.echo(
            json.dumps(
                {"error": str(error), "schema_version": 1, "status": "invalid"},
                sort_keys=True,
            )
        )
        raise typer.Exit(code=2) from error
    typer.echo(report.model_dump_json())
    if not report.valid:
        raise typer.Exit(code=3)


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
