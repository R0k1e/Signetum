"""Forward cases for decisions the repo-dev skill must preserve."""

from dataclasses import dataclass
from enum import Enum

import pytest


class Completion(Enum):
    OPEN = 0
    READY = 1
    INTEGRATED = 2
    DELIVERED = 3
    ACCEPTED = 4


@dataclass(frozen=True)
class ForwardCase:
    name: str
    manifest_change_root: str
    approved_obligations: frozenset[str]
    selected_obligations: frozenset[str]
    transferred_obligations: frozenset[str]
    evidence: Completion
    human_rejected: bool = False
    installed_skill: str = "2.0.0"
    pinned_skill: str = "2.0.0"


def evaluate(case: ForwardCase) -> tuple[str, Completion, bool]:
    """Project the required skill decision from supplied repository facts."""
    if case.installed_skill != case.pinned_skill:
        return case.manifest_change_root, Completion.OPEN, False

    uncovered = case.approved_obligations - case.selected_obligations - case.transferred_obligations
    if uncovered:
        return case.manifest_change_root, Completion.OPEN, False

    if case.human_rejected:
        return case.manifest_change_root, Completion.DELIVERED, True

    return case.manifest_change_root, case.evidence, False


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (
            ForwardCase(
                name="partial dispatch keeps plan open",
                manifest_change_root="governed/",
                approved_obligations=frozenset({"one", "two", "three", "four"}),
                selected_obligations=frozenset({"one", "two"}),
                transferred_obligations=frozenset(),
                evidence=Completion.READY,
            ),
            ("governed/", Completion.OPEN, False),
        ),
        (
            ForwardCase(
                name="manifest path is authoritative",
                manifest_change_root="work/",
                approved_obligations=frozenset({"one"}),
                selected_obligations=frozenset({"one"}),
                transferred_obligations=frozenset(),
                evidence=Completion.READY,
            ),
            ("work/", Completion.READY, False),
        ),
        (
            ForwardCase(
                name="member receipt proves ready only",
                manifest_change_root="governed/",
                approved_obligations=frozenset({"one"}),
                selected_obligations=frozenset({"one"}),
                transferred_obligations=frozenset(),
                evidence=Completion.READY,
            ),
            ("governed/", Completion.READY, False),
        ),
        (
            ForwardCase(
                name="rejection reopens without erasing delivery",
                manifest_change_root="governed/",
                approved_obligations=frozenset({"one"}),
                selected_obligations=frozenset({"one"}),
                transferred_obligations=frozenset(),
                evidence=Completion.DELIVERED,
                human_rejected=True,
            ),
            ("governed/", Completion.DELIVERED, True),
        ),
        (
            ForwardCase(
                name="installed version cannot override downstream pin",
                manifest_change_root="governed/",
                approved_obligations=frozenset({"one"}),
                selected_obligations=frozenset({"one"}),
                transferred_obligations=frozenset(),
                evidence=Completion.READY,
                installed_skill="2.1.0",
                pinned_skill="2.0.0",
            ),
            ("governed/", Completion.OPEN, False),
        ),
    ],
)
def test_forward_decisions(
    case: ForwardCase,
    expected: tuple[str, Completion, bool],
) -> None:
    assert evaluate(case) == expected
