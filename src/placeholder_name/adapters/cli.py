"""CLI adapter — the Composition Root.

This is the ONLY layer that:
  - Wires dependencies via Lagom
  - Loads configuration via Hydra
  - Converts exceptions to Result types (railway-oriented error handling)
  - Sets up observability (loguru)

Core layers must NOT be imported from here other than through Protocol types.
"""

import signal
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager

import hydra
import typer
import uvloop
from lagom import Container
from loguru import logger
from omegaconf import DictConfig
from returns.result import Failure, Result, Success, safe

from placeholder_name.config import AppConfig, LogLevel
from placeholder_name.core.protocols import Greeter
from placeholder_name.core.service import GreeterService

app = typer.Typer(no_args_is_help=False)


# ---------------------------------------------------------------------------
# Dependency wiring (Composition Root)
# ---------------------------------------------------------------------------


def _build_container() -> Container:
    """Wire all dependencies. Called once at startup."""
    container = Container()
    container.define(Greeter, lambda: GreeterService())
    return container


# ---------------------------------------------------------------------------
# System boundary helpers
# ---------------------------------------------------------------------------


@safe  # wraps exceptions into Failure; returns Success on normal return
def _run_greeting(greeter: Greeter, name: str) -> str:
    return greeter.greet(name)


@contextmanager
def _graceful_shutdown() -> Generator[None, None, None]:
    """Install SIGTERM handler to allow in-flight tasks to complete."""

    def _handle_sigterm(_signum: int, _frame: object) -> None:
        logger.warning("SIGTERM received — initiating graceful shutdown")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@app.command()
def greet(
    name: str = typer.Option("", help="Name to greet (overrides config)"),
) -> None:
    """Greet a user by name, using config/config.yml as default."""
    uvloop.install()

    with hydra.initialize(config_path="../../config", version_base=None):
        cfg: DictConfig = hydra.compose(config_name="config")

    # Validate config at system boundary — explicit fields ensure type safety.
    config = AppConfig(
        name=str(cfg.get("name", "World")),
        log_level=LogLevel(str(cfg.get("log_level", "INFO"))),
        output_dir=str(cfg.get("output_dir", "output")),
    )

    _configure_logger(config)

    target_name = name.strip() or config.name

    container = _build_container()
    greeter = container[Greeter]

    result: Result[str, Exception] = _run_greeting(greeter, target_name)

    with _graceful_shutdown():
        match result:
            case Success(message):
                logger.info("Greeting successful: {}", message)
                typer.echo(message)
            case Failure(exc):
                logger.error("Greeting failed: {}", exc)
                raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _configure_logger(config: AppConfig) -> None:
    logger.remove()
    logger.add(sys.stderr, level=config.log_level.value)
    logger.add(
        f"{config.output_dir}/{time.strftime('%Y-%m-%d_%H-%M-%S')}/app.log",
        rotation="10 MB",
        level=config.log_level.value,
    )
