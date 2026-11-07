"""Shared issue values and retained standalone decision relation checks."""

from dataclasses import dataclass

from signetum.change.models import (
    Decision,
    DecisionStatus,
)
from signetum.contract_values import FrozenContract


@dataclass(frozen=True, kw_only=True)
class TraceabilityIssue(FrozenContract):
    code: str
    file: str
    field: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class TraceabilityReport(FrozenContract):
    schema_version: int = 1
    valid: bool
    issues: tuple[TraceabilityIssue, ...]


_REFUSED_DECISION_STATUSES = frozenset({DecisionStatus.REJECTED, DecisionStatus.DRAFT})


def decision_corpus_issues(
    decisions: tuple[tuple[str, Decision], ...],
) -> tuple[TraceabilityIssue, ...]:
    """Refuse a corpus where a supersession is recorded on one side only.

    A supersession which only the successor records leaves every reader of the
    superseded decision believing it still stands.
    """

    by_name = {decision.name: decision for _, decision in decisions}
    issues: list[TraceabilityIssue] = []
    for path, decision in decisions:
        for replaced in decision.supersedes:
            target = by_name.get(replaced.rsplit("/", 1)[-1])
            if target is None:
                issues.append(
                    TraceabilityIssue(
                        code="dangling-supersession",
                        file=path,
                        field="Supersedes",
                        reason=f"supersedes an absent decision: {replaced}",
                    )
                )
            elif decision.name not in {item.rsplit("/", 1)[-1] for item in target.superseded_by}:
                issues.append(
                    TraceabilityIssue(
                        code="one-sided-supersession",
                        file=target.path,
                        field="Superseded by",
                        reason=f"does not record its supersession by {decision.name}",
                    )
                )
    return tuple(issues)
