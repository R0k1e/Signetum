"""Core domain protocols.

Defines abstract boundaries via typing.Protocol (structural subtyping).
No adapter imports allowed in this layer.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Greeter(Protocol):
    """Contract for any greeting implementation."""

    def greet(self, name: str) -> str:
        """Return a greeting string for the given name."""
        ...
