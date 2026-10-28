# Generated from signetum.operations; edit the engine source and regenerate.
"""One result and exit-code contract for repository lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OperationStatus(StrEnum):
    PASSED = "passed"
    INVALID = "invalid"
    FAILED = "failed"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    CONFLICT = "conflict"


EXIT_CODES = {
    OperationStatus.PASSED: 0,
    OperationStatus.INVALID: 2,
    OperationStatus.FAILED: 3,
    OperationStatus.INFRASTRUCTURE_ERROR: 4,
    OperationStatus.CONFLICT: 5,
}


class OperationError(ValueError):
    """A refused or incomplete operation, with its supported next action."""

    status = OperationStatus.INVALID

    def __init__(self, cause: str, *, expected: str = "correct the precondition and retry"):
        super().__init__(cause)
        self.expected = expected


class AdmissionError(OperationError):
    """A lifecycle precondition cannot be established safely."""


class InfrastructureError(OperationError):
    """The operation could not obtain a verdict."""

    status = OperationStatus.INFRASTRUCTURE_ERROR


class OperationFailed(OperationError):
    """An executed operation failed."""

    status = OperationStatus.FAILED


class MergeConflict(OperationError):
    """An open Git merge requires supported continuation."""

    status = OperationStatus.CONFLICT


@dataclass(frozen=True)
class OperationResult:
    operation: str
    status: OperationStatus
    fields: dict[str, object]
    cause: str | None = None
    expected: str | None = None
    log: str | None = None

    def document(self) -> dict[str, object]:
        """Project operation payload without allowing it to replace envelope fields."""

        document = {
            **self.fields,
            "schema_version": 1,
            "operation": self.operation,
            "status": self.status.value,
            "exit_code": EXIT_CODES[self.status],
        }
        if self.status != OperationStatus.PASSED:
            document.update(
                cause=self.cause,
                context={"operation": self.operation},
                expected=self.expected,
                log=self.log,
            )
        return document
