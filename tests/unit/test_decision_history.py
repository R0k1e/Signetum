"""The current set comes from explicit accepted history, not input ordering."""

import importlib
from dataclasses import replace
from pathlib import Path

import pytest
from signetum import decision_clauses as clauses
from signetum import decision_history as history


@pytest.fixture(autouse=True, params=["engine"])
def backend(request, monkeypatch):
    if request.param == "template":
        monkeypatch.syspath_prepend(
            str(
                Path(__file__).parents[2]
                / "tests/fixtures/portable-python/.agents/signetum/runtime"
            )
        )
        for name in ("clauses", "history"):
            monkeypatch.setitem(
                globals(), name, importlib.import_module("_signetum_runtime.decision_" + name)
            )


@pytest.fixture
def initial():
    rows = tuple(
        clauses.ClauseRevision(
            id=f"VAL-00{number}",
            version=1,
            topic="validation",
            scope=("repository",),
            statement=f"Validation choice {number}.",
            rationale=f"Original reason {number}.",
        )
        for number in range(1, 4)
    )
    edit = clauses.DecisionEdit(
        id="first/clauses",
        change_id="first",
        action="add",
        expected=tuple(clauses.ExpectedClause(id=row.id, version=0) for row in rows),
        updates=rows,
        reason="Initial approved choices.",
        authority="first/contract",
    )
    return history.DecisionTransaction(
        id="first/transaction",
        change_id="first",
        authority="first/contract",
        reason="Establish the validation boundary.",
        clauses=(edit,),
        topics=(
            history.TopicEdit(
                expected_version=0,
                revision=history.TopicRevision(
                    id="validation",
                    version=1,
                    summary="Validation proves the exact change inputs.",
                    boundaries=("Test success is not delivery authorization.",),
                ),
            ),
        ),
    )


def amendment(initial, *, identity="second", index=1):
    row = initial.clauses[0].updates[index]
    revised = replace(row, version=2, statement="Keep failures failed after diagnostic retry.")
    return history.DecisionTransaction(
        id=f"{identity}/transaction",
        change_id=identity,
        parents=(initial.id,),
        reason="Refine one rule.",
        authority=f"{identity}/contract",
        clauses=(
            clauses.DecisionEdit(
                id=f"{identity}/edit",
                change_id=identity,
                action="amend",
                expected=(clauses.ExpectedClause(id=row.id, version=1),),
                updates=(revised,),
                reason="A diagnostic retry does not prove the normal workload.",
                authority=f"{identity}/contract",
            ),
        ),
    )


def test_current_context_and_unaffected_rules_survive_a_partial_change(initial):
    event = amendment(initial)
    projected = history.project_decision_history((initial, event))
    reordered = history.project_decision_history((event, initial))
    assert reordered == projected
    assert projected.topics[0].revision.summary == initial.topics[0].revision.summary
    assert projected.topics[0].revision.boundaries == initial.topics[0].revision.boundaries
    assert projected.clauses[0].revision == initial.clauses[0].updates[0]
    assert projected.clauses[2].revision == initial.clauses[0].updates[2]
    assert projected.clauses[1].source_event == event.clauses[0].id
    assert projected.clauses[1].revision.version == 2


def test_independent_changes_combine_without_whole_topic_override(initial):
    one, two = amendment(initial, index=0), amendment(initial, identity="third", index=2)
    result = history.project_decision_history((two, initial, one))
    assert [item.revision.version for item in result.clauses] == [2, 1, 2]


def test_concurrent_changes_of_the_same_clause_are_not_ordered_by_filename(initial):
    one, two = amendment(initial), amendment(initial, identity="third")
    for events in ((initial, one, two), (two, one, initial)):
        with pytest.raises(clauses.DecisionEditError, match="concurrent"):
            history.project_decision_history(events)


def test_topic_context_can_evolve_without_rewriting_the_rules(initial):
    revised = replace(
        initial.topics[0].revision, version=2, summary="A revised overall explanation."
    )
    event = history.DecisionTransaction(
        id="second/topic",
        change_id="second",
        parents=(initial.id,),
        authority="second/contract",
        reason="Clarify current context.",
        topics=(history.TopicEdit(expected_version=1, revision=revised),),
    )
    result = history.project_decision_history((initial, event))
    assert result.topics[0].revision == revised
    assert result.topics[0].source_event == event.id
    assert result.clauses == history.project_decision_history((initial,)).clauses


def test_a_clause_requires_an_explicit_overall_topic(initial):
    with pytest.raises(clauses.DecisionEditError, match="no topic context"):
        history.project_decision_history((replace(initial, topics=()),))


@pytest.mark.parametrize("damage", ["duplicate", "missing-parent", "cycle", "stale-topic"])
def test_invalid_history_never_produces_a_current_set(initial, damage):
    if damage == "duplicate":
        events = (initial, initial)
    elif damage == "missing-parent":
        events = (replace(initial, parents=("missing",)),)
    elif damage == "cycle":
        events = (replace(initial, parents=(initial.id,)),)
    else:
        bad = replace(initial.topics[0], expected_version=8)
        events = (replace(initial, topics=(bad,)),)
    with pytest.raises(clauses.DecisionEditError):
        history.project_decision_history(events)


@pytest.mark.parametrize(
    "damage",
    [
        "empty",
        "duplicate-write",
        "foreign-owner",
        "foreign-authority",
        "duplicate-parent",
        "ambiguous-event",
    ],
)
def test_transactions_cannot_hide_ambiguous_ownership_or_identity(initial, damage):
    if damage == "empty":
        event = replace(initial, clauses=(), topics=())
    elif damage == "duplicate-write":
        event = replace(initial, topics=initial.topics * 2)
    elif damage == "foreign-owner":
        event = replace(initial, clauses=(replace(initial.clauses[0], change_id="other"),))
    elif damage == "foreign-authority":
        event = replace(initial, clauses=(replace(initial.clauses[0], authority="other/contract"),))
    elif damage == "duplicate-parent":
        event = replace(initial, parents=(initial.id, initial.id))
    else:
        event = replace(initial, clauses=(replace(initial.clauses[0], id=initial.id),))
    with pytest.raises(clauses.DecisionEditError):
        history.project_decision_history((event,))


@pytest.mark.parametrize("requires", [("absent-topic",), ("validation",)])
def test_the_overall_topic_map_cannot_have_missing_or_cyclic_context(initial, requires):
    topic = replace(initial.topics[0].revision, requires=requires)
    event = replace(initial, topics=(replace(initial.topics[0], revision=topic),))
    with pytest.raises(clauses.DecisionEditError, match="topic relationship"):
        history.project_decision_history((event,))
