"""Decision edits preserve unaffected clauses and refuse lost updates."""

import importlib
from dataclasses import replace
from pathlib import Path

import pytest

from signetum.decision_clauses import (
    ClauseRevision,
    DecisionEdit,
    DecisionEditError,
    EffectiveClause,
    ExpectedClause,
    apply_decision_edits,
)


@pytest.fixture(autouse=True, params=["engine", "template"])
def authority(request, monkeypatch):
    if request.param == "template":
        monkeypatch.syspath_prepend(
            str(Path(__file__).parents[2] / "template/.agents/repo-dev/runtime")
        )
        generated = importlib.import_module("_signetum_runtime.decision_clauses")
        for name in (
            "ClauseRevision",
            "DecisionEdit",
            "DecisionEditError",
            "EffectiveClause",
            "ExpectedClause",
            "apply_decision_edits",
        ):
            monkeypatch.setitem(globals(), name, getattr(generated, name))


def clause(identity, **values):
    return ClauseRevision(
        id=identity,
        version=1,
        topic="validation",
        scope=("repository",),
        statement=f"Rule {identity}",
        rationale=f"Reason {identity}",
        **values,
    )


def edit(action, expected, updates, identity="change/event"):
    return DecisionEdit(
        id=identity,
        change_id="change",
        action=action,
        expected=tuple(ExpectedClause(id=key, version=value) for key, value in expected.items()),
        updates=tuple(updates),
        reason="Owner-approved targeted change.",
        authority="changes/change/change.toml#approval",
    )


@pytest.fixture
def current():
    return tuple(
        EffectiveClause(revision=clause(key), source_event="initial/event")
        for key in ("VAL-001", "VAL-002", "VAL-003")
    )


def test_partial_amendment_preserves_unaffected_values_and_provenance(current):
    revised = replace(current[1].revision, version=2, statement="Retry is diagnostic only.")
    result = apply_decision_edits(current, (edit("amend", {"VAL-002": 1}, [revised]),))
    assert result[0] is current[0]
    assert result[2] is current[2]
    assert result[1].revision == revised
    assert result[1].source_event == "change/event"
    assert current[1].revision.version == 1


def test_concurrent_amendment_cannot_replace_a_newer_revision(current):
    revised = replace(current[1].revision, version=2, statement="First approved amendment.")
    transaction = edit("amend", {"VAL-002": 1}, [revised])
    updated = apply_decision_edits(current, (transaction,))
    with pytest.raises(DecisionEditError, match="stale"):
        apply_decision_edits(updated, (replace(transaction, id="other/event"),))
    assert updated[1].revision == revised


def test_a_failed_transaction_does_not_apply_its_valid_prefix(current):
    first = edit(
        "amend", {"VAL-002": 1}, [replace(current[1].revision, version=2, statement="New rule.")]
    )
    wrong = edit(
        "withdraw",
        {"VAL-003": 7},
        [replace(current[2].revision, version=8, status="withdrawn")],
        "change/second",
    )
    with pytest.raises(DecisionEditError, match="stale"):
        apply_decision_edits(current, (first, wrong))
    assert all(item.revision.version == 1 for item in current)


def test_split_and_merge_preserve_the_original_clauses_as_withdrawn(current):
    split = edit(
        "split",
        {"VAL-002": 1, "VAL-004": 0, "VAL-005": 0},
        [
            replace(current[1].revision, version=2, status="withdrawn"),
            clause("VAL-004"),
            clause("VAL-005"),
        ],
    )
    divided = apply_decision_edits(current, (split,))
    versions = {item.revision.id: item.revision for item in divided}
    assert versions["VAL-002"].status == "withdrawn"
    merge = edit(
        "merge",
        {"VAL-004": 1, "VAL-005": 1, "VAL-006": 0},
        [replace(versions[key], version=2, status="withdrawn") for key in ("VAL-004", "VAL-005")]
        + [clause("VAL-006")],
        "change/merge",
    )
    merged = apply_decision_edits(divided, (merge,))
    assert {item.revision.id for item in merged if item.revision.status == "active"} == {
        "VAL-001",
        "VAL-003",
        "VAL-006",
    }
    assert merged[0] is current[0] and merged[2] is current[2]


@pytest.mark.parametrize("requires", [("absent",), ("VAL-002",)])
def test_new_requirements_cannot_be_missing_or_cyclic(current, requires):
    revised = replace(current[1].revision, version=2, requires=requires)
    with pytest.raises(DecisionEditError, match="requirement"):
        apply_decision_edits(current, (edit("amend", {"VAL-002": 1}, [revised]),))


def test_withdrawal_cannot_silently_rewrite_the_old_decision(current):
    revision = replace(current[1].revision, version=2, status="withdrawn", statement="Different.")
    with pytest.raises(DecisionEditError, match="preserves"):
        apply_decision_edits(current, (edit("withdraw", {"VAL-002": 1}, [revision]),))


def test_every_changed_clause_requires_an_explicit_expected_version(current):
    event = edit(
        "amend",
        {"VAL-002": 1},
        [
            replace(current[1].revision, version=2, statement="New."),
            replace(current[2].revision, version=2, statement="Other."),
        ],
    )
    with pytest.raises(DecisionEditError, match="every updated clause"):
        apply_decision_edits(current, (event,))


def test_withdraw_and_restore_keep_the_identity_and_advance_versions(current):
    withdrawn = replace(current[1].revision, version=2, status="withdrawn")
    updated = apply_decision_edits(current, (edit("withdraw", {"VAL-002": 1}, [withdrawn]),))
    assert updated[1].revision == withdrawn
    assert updated[0] is current[0] and updated[2] is current[2]
    restored = replace(withdrawn, version=3, status="active")
    result = apply_decision_edits(
        updated, (edit("amend", {"VAL-002": 2}, [restored], "change/restore"),)
    )
    assert result[1].revision == restored
    assert result[1].source_event == "change/restore"


def test_withdrawing_a_dependency_requires_explicit_consumer_repair(current):
    dependent = replace(current[0], revision=replace(current[0].revision, requires=("VAL-002",)))
    current = (dependent, *current[1:])
    withdrawal = edit(
        "withdraw", {"VAL-002": 1}, [replace(current[1].revision, version=2, status="withdrawn")]
    )
    with pytest.raises(DecisionEditError, match="absent or withdrawn"):
        apply_decision_edits(current, (withdrawal,))
    repair = edit(
        "amend",
        {"VAL-001": 1},
        [replace(dependent.revision, version=2, requires=())],
        "change/repair",
    )
    result = apply_decision_edits(current, (withdrawal, repair))
    assert result[0].revision.requires == ()
    assert result[2] is current[2]


@pytest.mark.parametrize(
    "action,old_count,new_count",
    [
        ("add", 1, 0),
        ("amend", 0, 1),
        ("withdraw", 0, 1),
        ("split", 1, 1),
        ("merge", 1, 1),
    ],
)
def test_edit_kind_must_describe_its_actual_affected_set(current, action, old_count, new_count):
    expected = {item.revision.id: 1 for item in current[:old_count]}
    expected.update({f"NEW-{index}": 0 for index in range(new_count)})
    updates = [replace(item.revision, version=2) for item in current[:old_count]]
    updates.extend(clause(f"NEW-{index}") for index in range(new_count))
    with pytest.raises(DecisionEditError, match="invalid affected"):
        apply_decision_edits(current, (edit(action, expected, updates),))


@pytest.mark.parametrize("version,statement", [(2, "Rule VAL-002"), (3, "Changed rule.")])
def test_amendment_cannot_hide_a_noop_or_skip_a_version(current, version, statement):
    candidate = replace(current[1].revision, version=version, statement=statement)
    with pytest.raises(DecisionEditError, match=r"change the clause|exactly one version"):
        apply_decision_edits(current, (edit("amend", {"VAL-002": 1}, [candidate]),))


def test_duplicate_identifiers_cannot_make_an_edit_ambiguous(current):
    candidate = replace(current[1].revision, version=2, statement="Changed.")
    event = edit("amend", {"VAL-002": 1}, [candidate])
    with pytest.raises(DecisionEditError, match="duplicate expected"):
        apply_decision_edits(current, (replace(event, expected=event.expected * 2),))
    with pytest.raises(DecisionEditError, match="duplicate updated"):
        apply_decision_edits(current, (replace(event, updates=event.updates * 2),))
    with pytest.raises(DecisionEditError, match="duplicate current"):
        apply_decision_edits(current * 2, (event,))
    with pytest.raises(DecisionEditError, match="duplicate decision event"):
        apply_decision_edits(current, (event, event))
