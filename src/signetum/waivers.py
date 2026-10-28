"""Tracked, approved, and expiring coverage for world shard findings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from re import fullmatch
from tomllib import TOMLDecodeError, loads

from signetum.findings import Finding

WAIVER_GLOB = "changes/*/waivers/*.toml"


class WaiverError(ValueError):
    """A tracked waiver violates the approved coverage contract."""


@dataclass(frozen=True)
class Waiver:
    """One human-approved, expiring exception for named world findings."""

    schema_version: int
    id: str
    shard: str
    findings: tuple[str, ...]
    reason: str
    approved_by: str
    expires: date
    follow_up: str | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise WaiverError(f"unsupported waiver schema: {self.schema_version}")
        for name in ("id", "shard"):
            value = getattr(self, name)
            if not isinstance(value, str) or fullmatch(r"[a-z0-9][a-z0-9._:@-]*", value) is None:
                raise WaiverError(f"{name}: waiver identifier must be lowercase and namespaced")
        if not isinstance(self.findings, tuple) or not self.findings:
            raise WaiverError("findings must contain at least 1 item")
        for item in self.findings:
            if (
                not isinstance(item, str)
                or fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@/-]*", item) is None
            ):
                raise WaiverError(f"waived finding must be an identifier: {item}")
        if len(self.findings) != len(set(self.findings)):
            raise WaiverError("waiver findings must be unique")
        for name in ("reason", "approved_by"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise WaiverError(f"{name} must be non-empty")
        if type(self.expires) is not date:
            raise WaiverError("expires must be a date")
        if self.follow_up is not None and (
            not isinstance(self.follow_up, str) or not self.follow_up.strip()
        ):
            raise WaiverError("follow_up must be a non-empty string when provided")

    def usable(self, *, today: date) -> bool:
        """Report whether this waiver still carries authority on the given day."""

        return self.expires >= today


def parse_waiver(raw: object) -> Waiver:
    """Normalize a versioned document once, then validate the immutable value."""

    required = {"schema_version", "id", "shard", "findings", "reason", "approved_by", "expires"}
    if not isinstance(raw, dict):
        raise WaiverError("waiver must be an object")
    if missing := required - raw.keys():
        raise WaiverError("waiver is missing " + ", ".join(sorted(missing)))
    if raw.keys() - required - {"follow_up"}:
        raise WaiverError("waiver carries unsupported fields")
    fields = dict(raw)
    findings = fields["findings"]
    if isinstance(findings, list):
        fields["findings"] = tuple(findings)
    expires = fields["expires"]
    if isinstance(expires, str):
        try:
            fields["expires"] = date.fromisoformat(expires)
        except ValueError as error:
            raise WaiverError("expires must be a date") from error
    return Waiver(**fields)


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
            waivers.append(parse_waiver(document["waiver"]))
        except WaiverError as error:
            raise WaiverError(f"{relative}: {error}") from error
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
    "parse_waiver",
]
