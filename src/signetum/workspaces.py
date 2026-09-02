"""One durable record of what a workspace is and which base it was cut from."""

from __future__ import annotations

import json
from pathlib import Path
from re import fullmatch
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

WORKSPACE_DIRECTORY = "workspaces"


class WorkspaceError(ValueError):
    """A workspace record is missing, malformed, or already claimed."""


class WorkspaceRecord(BaseModel):
    """What a workspace is, written once when the workspace is created."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    branch: str = Field(min_length=1)
    base: str
    kind: Literal["member", "batch"]
    members: tuple[str, ...] = ()

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"unsupported workspace record schema: {value}")
        return value

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str) -> str:
        if fullmatch(r"[0-9a-f]{40,64}", value) is None:
            raise ValueError("workspace base must be an exact commit identity")
        return value

    @field_validator("members")
    @classmethod
    def validate_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("declared members must be unique")
        return value


def record_path(root: Path, branch: str) -> Path:
    """Return the record location for one branch inside the state root."""

    return root / WORKSPACE_DIRECTORY / f"{quote(branch, safe='')}.json"


def write_record(root: Path, record: WorkspaceRecord) -> Path:
    """Write one workspace record, refusing to restate an existing base.

    A base is written once. Rewriting it would make the record a second place
    to claim a base rather than the single place that holds one.
    """

    path = record_path(root, record.branch)
    if path.exists():
        existing = read_record(root, record.branch)
        if existing.base != record.base:
            raise WorkspaceError(
                f"workspace {record.branch} is already recorded at base {existing.base}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_record(root: Path, branch: str) -> WorkspaceRecord:
    """Read the record for one branch, failing closed when it is unusable."""

    path = record_path(root, branch)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        # A base is never guessed. A workspace created before this record
        # existed is adopted by writing the base a human knows it was cut
        # from, once, at the named path.
        raise WorkspaceError(
            f"workspace {branch} has no recorded base at {path}; "
            "a workspace created by workspace-open carries one, and one created "
            "earlier is adopted by writing "
            '{"schema_version": 1, "branch": ..., "base": ..., "kind": "member"} '
            "there"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise WorkspaceError(f"workspace record for {branch} is unreadable: {error}") from error
    try:
        return WorkspaceRecord.model_validate(document)
    except ValidationError as error:
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        message = str(first["msg"]).removeprefix("Value error, ")
        raise WorkspaceError(
            f"workspace record for {branch} is invalid: {f'{field}: ' if field else ''}{message}"
        ) from error


__all__ = [
    "WORKSPACE_DIRECTORY",
    "WorkspaceError",
    "WorkspaceRecord",
    "read_record",
    "record_path",
    "write_record",
]
