"""CLI adapter integration tests.

Uses Typer's CliRunner and unittest.mock to isolate the CLI from
Hydra configuration loading and the file system.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

from typer.testing import CliRunner

from placeholder_name.adapters.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_hydra_cfg(name: str = "Test", log_level: str = "INFO", output_dir: str = "/tmp") -> MagicMock:
    """Return a minimal DictConfig-like mock."""
    cfg = MagicMock()
    values = {"name": name, "log_level": log_level, "output_dir": output_dir}
    cfg.get.side_effect = lambda k, default=None: values.get(k, default)
    return cfg


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

def test_greet_default_name_from_config() -> None:
    cfg = _mock_hydra_cfg(name="ConfigWorld")
    with (
        patch("placeholder_name.adapters.cli.uvloop"),
        patch("placeholder_name.adapters.cli.hydra") as mock_hydra,
        patch("placeholder_name.adapters.cli._configure_logger"),
    ):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_hydra.initialize.return_value = ctx
        mock_hydra.compose.return_value = cfg

        result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Hello ConfigWorld!" in result.output


def test_greet_name_flag_overrides_config() -> None:
    cfg = _mock_hydra_cfg(name="ConfigWorld")
    with (
        patch("placeholder_name.adapters.cli.uvloop"),
        patch("placeholder_name.adapters.cli.hydra") as mock_hydra,
        patch("placeholder_name.adapters.cli._configure_logger"),
    ):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_hydra.initialize.return_value = ctx
        mock_hydra.compose.return_value = cfg

        result = runner.invoke(app, ["--name", "Alice"])

    assert result.exit_code == 0
    assert "Hello Alice!" in result.output


# ---------------------------------------------------------------------------
# Failure path (railway-oriented error handling)
# ---------------------------------------------------------------------------

def test_greet_exits_with_code_1_on_empty_name() -> None:
    """Empty name violates icontract precondition → Failure → exit code 1."""
    cfg = _mock_hydra_cfg(name="")
    with (
        patch("placeholder_name.adapters.cli.uvloop"),
        patch("placeholder_name.adapters.cli.hydra") as mock_hydra,
        patch("placeholder_name.adapters.cli._configure_logger"),
    ):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_hydra.initialize.return_value = ctx
        mock_hydra.compose.return_value = cfg

        result = runner.invoke(app, [])

    assert result.exit_code == 1
