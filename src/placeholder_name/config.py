"""Application configuration models.

Uses Pydantic V2 with frozen=True to enforce immutability across boundaries.
Enum types replace Literal strings per coding standards.
"""

from enum import Enum

from pydantic import BaseModel, Field


class LogLevel(Enum):
    """Logging verbosity level."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AppConfig(BaseModel, frozen=True):
    """Top-level application configuration.

    Loaded from config/config.yml via Hydra and validated at the system boundary.
    All fields are immutable after construction (frozen=True).
    """

    name: str = Field(default="World", min_length=1, description="Target name")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Log verbosity")
    output_dir: str = Field(default="output", description="Directory for log files")
