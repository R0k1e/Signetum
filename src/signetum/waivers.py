"""Tracked, approved, and expiring coverage for world shard findings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from re import fullmatch
from tomllib import TOMLDecodeError, loads

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from signetum.findings import Finding

WAIVER_GLOB = "changes/*/waivers/*.toml"


class WaiverError(ValueError):
    """A tracked waiver violates the approved coverage contract."""


class Waiver(BaseModel):
    """One human-approved, expiring exception for named world findings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    id: str
    shard: str
    findings: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    expires: date
    follow_up: str | None = None

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"unsupported waiver schema: {value}")
        return value

    @field_validator("id", "shard")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if fullmatch(r"[a-z0-9][a-z0-9._:@-]*", value) is None:
            raise ValueError(f"waiver identifier must be lowercase and namespaced: {value}")
        return value

    @field_validator("findings")
    @classmethod
    def validate_findings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("waiver findings must be unique")
        for item in value:
            if fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@/-]*", item) is None:
                raise ValueError(f"waived finding must be an identifier: {item}")
        return value

    def usable(self, *, today: date) -> bool:
        """Report whether this waiver still carries authority on the given day."""

        return self.expires >= today


@dataclass(frozen=True)
class WaiverOutcome:
    """Why a failing world shard was or was not covered."""

    covered: bool
    waivers: tuple[str, ...]
    findings: tuple[str, ...]
    uncovered: tuple[str, ...]
    expired: tuple[str, ...]

    def diagnostic(self, shard: str) -> str:
        """Explain an uncovered result in one operator-readable sentence."""

        parts = [f"world shard {shard} reported unwaived findings"]
        if self.uncovered:
            parts.append(f"uncovered: {', '.join(self.uncovered)}")
        if self.expired:
            parts.append(f"expired waivers: {', '.join(self.expired)}")
        return "; ".join(parts)


def load_waivers(repository: Path) -> tuple[Waiver, ...]:
    """Read every tracked waiver from the observed worktree."""

    waivers: list[Waiver] = []
    for path in sorted(repository.glob(WAIVER_GLOB)):
        relative = path.relative_to(repository).as_posix()
        try:
            document = loads(path.read_text(encoding="utf-8"))
        except (OSError, TOMLDecodeError) as error:
            raise WaiverError(f"{relative}: {error}") from error
        if set(document) != {"waiver"}:
            raise WaiverError(f"{relative}: file must declare exactly one [waiver] table")
        try:
            waivers.append(Waiver.model_validate(document["waiver"]))
        except ValidationError as error:
            first = error.errors()[0]
            field = ".".join(str(part) for part in first["loc"])
            message = str(first["msg"]).removeprefix("Value error, ")
            raise WaiverError(f"{relative}: {f'{field}: ' if field else ''}{message}") from error
    identities = [waiver.id for waiver in waivers]
    duplicates = sorted({item for item in identities if identities.count(item) > 1})
    if duplicates:
        raise WaiverError(f"duplicate waiver identities: {', '.join(duplicates)}")
    return tuple(waivers)


def cover_findings(
    shard: str,
    findings: tuple[Finding, ...],
    waivers: tuple[Waiver, ...],
    *,
    today: date,
) -> WaiverOutcome:
    """Decide whether every reported finding is covered by live authority.

    An empty finding set is never coverage: a world shard that failed without
    reporting anything cannot be explained, so it stays uncovered.
    """

    applicable = tuple(waiver for waiver in waivers if waiver.shard == shard)
    live = {waiver.id: waiver for waiver in applicable if waiver.usable(today=today)}
    stale = {waiver.id: waiver for waiver in applicable if not waiver.usable(today=today)}
    reported = tuple(sorted({finding.id for finding in findings}))
    used: set[str] = set()
    uncovered: list[str] = []
    expired: set[str] = set()
    for identifier in reported:
        covering = sorted(item.id for item in live.values() if identifier in item.findings)
        if covering:
            used.update(covering)
            continue
        uncovered.append(identifier)
        expired.update(item.id for item in stale.values() if identifier in item.findings)
    return WaiverOutcome(
        covered=bool(reported) and not uncovered,
        waivers=tuple(sorted(used)),
        findings=reported,
        uncovered=tuple(uncovered),
        expired=tuple(sorted(expired)),
    )


__all__ = [
    "WAIVER_GLOB",
    "Waiver",
    "WaiverError",
    "WaiverOutcome",
    "cover_findings",
    "load_waivers",
]
