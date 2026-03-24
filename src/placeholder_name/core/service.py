"""Core domain service implementations.

Business logic lives here. No I/O, no framework imports.
Contracts are enforced via icontract pre/post-conditions.
"""

import icontract

from placeholder_name.core.protocols import Greeter


class GreeterService:
    """Concrete implementation of the Greeter protocol.

    Satisfies Greeter structurally — no explicit inheritance required.
    """

    @icontract.require(
        lambda name: len(name.strip()) > 0,
        "Name must be non-empty after stripping",
    )
    @icontract.ensure(
        lambda result: result.startswith("Hello"),
        "Result must start with 'Hello'",
    )
    def greet(self, name: str) -> str:
        """Return a personalised greeting."""
        return f"Hello {name.strip()}!"


def _assert_protocol_satisfied() -> None:
    """Fail fast at import time if GreeterService breaks the Greeter contract."""
    if not isinstance(GreeterService(), Greeter):
        msg = "GreeterService must satisfy the Greeter protocol"
        raise TypeError(msg)


_assert_protocol_satisfied()
