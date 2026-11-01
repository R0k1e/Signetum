"""Check-only public command line interface."""

import json
from pathlib import Path
from typing import Annotated

import typer
from signetum.git import GitError
from signetum.operation_cli import utility_failure
from signetum.serialization import json_value
from signetum.traceability.boundary import GitInventoryProvider

from tools.product_surface import validate_product_surface
from tools.release import preflight
from tools.site import build_site

app = typer.Typer(add_completion=False, help="Maintain the Signetum repository.")
release_app = typer.Typer(add_completion=False)
app.add_typer(release_app, name="release")
site_app = typer.Typer(add_completion=False)
app.add_typer(site_app, name="site")
check_app = typer.Typer(add_completion=False)
app.add_typer(check_app, name="check")


@site_app.command("build")
def site_build(
    repository: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    destination: Annotated[Path, typer.Option()] = Path(".pages-artifact"),
) -> None:
    """Build an exact, disposable GitHub Pages artifact."""
    try:
        files = build_site(repository.resolve(), destination.resolve())
    except (OSError, ValueError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "invalid"}, sort_keys=True))
        raise typer.Exit(code=3) from error
    typer.echo(json.dumps({"files": len(files), "status": "built"}, sort_keys=True))


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
    typer.echo(json.dumps(json_value(report)))
    if not report.valid:
        raise typer.Exit(code=3)


@release_app.command("preflight")
def release_preflight(
    source: Annotated[str, typer.Option()],
    repository: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    tag: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Check an exact delivered engine source without granting publication."""
    try:
        metadata = preflight(repository.resolve(), source, tag=tag)
    except (OSError, ValueError, GitError) as error:
        raise typer.Exit(code=utility_failure("release-preflight", error)) from error
    typer.echo(
        json.dumps(
            {"schema_version": 1, "status": "valid", "release": metadata.model_dump(mode="json")},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    app()
