"""One public command tree; the Skill launcher forwards arguments unchanged."""

from importlib import import_module

import typer

from signetum.commands import BOOTSTRAP, COMMANDS, Command

app = typer.Typer(
    add_completion=False,
    help="Reliable Agent development and delivery.",
    epilog="Installed Skill setup and updates: "
    + "; ".join(f"{name}: {help}" for name, help in BOOTSTRAP.items()),
)
_PASSTHROUGH = {
    "allow_extra_args": True,
    "ignore_unknown_options": True,
    "allow_interspersed_args": False,
}


def _callback(command: Command):
    def invoke(ctx: typer.Context) -> None:
        owner = import_module("signetum." + command.module)
        handler = getattr(owner, command.function)
        raise typer.Exit(code=handler([*command.prefix, *ctx.args, *command.suffix]))

    return invoke


def build_app() -> typer.Typer:
    groups: dict[tuple[str, ...], typer.Typer] = {(): app}
    for command in COMMANDS:
        parent = command.path[:-1]
        if parent not in groups:
            groups[parent] = typer.Typer(
                add_completion=False,
                help={
                    "change": "Approved changes, significant history and current decisions.",
                    "test": "Feedback and optional test optimization.",
                    "adopt": "Explicit project adoption.",
                    "check": "Read-only repository checks.",
                }[parent[0]],
            )
            app.add_typer(groups[parent], name=parent[0], rich_help_panel=command.panel)
        callback = (
            _callback(command)
            if command.passthrough
            else getattr(import_module("signetum." + command.module), command.function)
        )
        groups[parent].command(
            name=command.path[-1],
            help=command.help,
            context_settings=_PASSTHROUGH if command.passthrough else None,
            add_help_option=not command.passthrough,
            rich_help_panel=command.panel,
        )(callback)
    return app


build_app()
if __name__ == "__main__":
    app()
