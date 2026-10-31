"""Shared native construction guard for frozen, portable contract values."""

from signetum.serialization import validate_dataclass


class FrozenContract:
    """Dataclass owners retain one typed boundary for loaded and native values."""

    def __post_init__(self) -> None:
        validate_dataclass(self)
