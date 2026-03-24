"""Tests for application configuration models.

Uses Hypothesis for property-based validation of Pydantic boundary contracts.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from placeholder_name.config import AppConfig
from placeholder_name.config import LogLevel


# ---------------------------------------------------------------------------
# LogLevel enum
# ---------------------------------------------------------------------------

def test_log_level_has_expected_values() -> None:
    assert {e.value for e in LogLevel} == {"DEBUG", "INFO", "WARNING", "ERROR"}


# ---------------------------------------------------------------------------
# AppConfig immutability (frozen=True)
# ---------------------------------------------------------------------------

def test_app_config_is_frozen() -> None:
    config = AppConfig()
    with pytest.raises(ValidationError):
        config.name = "mutated"  # type: ignore[misc]  # intentional mutation attempt


def test_app_config_frozen_log_level_raises() -> None:
    config = AppConfig()
    with pytest.raises(ValidationError):
        config.log_level = LogLevel.ERROR  # type: ignore[misc]  # intentional mutation attempt


# ---------------------------------------------------------------------------
# AppConfig defaults
# ---------------------------------------------------------------------------

def test_app_config_defaults() -> None:
    config = AppConfig()
    assert config.name == "World"
    assert config.log_level is LogLevel.INFO
    assert config.output_dir == "output"


def test_app_config_custom_values() -> None:
    config = AppConfig(name="Alice", log_level=LogLevel.DEBUG, output_dir="/tmp/logs")
    assert config.name == "Alice"
    assert config.log_level is LogLevel.DEBUG


def test_app_config_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        AppConfig(name="")


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

@pytest.mark.slow
@given(name=st.text(min_size=1, max_size=200))
def test_app_config_accepts_any_non_empty_name(name: str) -> None:
    config = AppConfig(name=name)
    assert config.name == name


@pytest.mark.slow
@given(level=st.sampled_from(LogLevel))
def test_app_config_accepts_all_log_levels(level: LogLevel) -> None:
    config = AppConfig(log_level=level)
    assert config.log_level is level
