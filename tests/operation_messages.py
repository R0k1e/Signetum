"""Caller commit messages for automatic Signetum operations in tests."""

import tempfile
from pathlib import Path


def operation_message(subject: str = "Record the reviewed source change.") -> str:
    """One frozen message. The project convention is a durable subject, not a type."""

    return f"{subject}\n"


def operation_messages(count: int) -> tuple[str, ...]:
    """One distinct message per member. An empty admission passes an empty tuple."""

    if count == 0:
        return ()
    if count == 1:
        return (operation_message(),)
    return tuple(
        operation_message(f"Record reviewed source change {index}.")
        for index in range(1, count + 1)
    )


def write_operation_message(
    directory: Path | None = None,
    *,
    name: str = "message.txt",
    text: str | None = None,
) -> Path:
    """Write a message file outside a worktree unless the caller names a directory."""

    folder = directory
    if folder is None:
        folder = Path(tempfile.mkdtemp(prefix="signetum-message-"))
    path = folder / name
    path.write_text(operation_message() if text is None else text, encoding="utf-8")
    return path
