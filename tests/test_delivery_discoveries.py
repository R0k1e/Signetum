"""Final reviews discoveries of exact admitted members and stable decision identities."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from change_fixtures import approve_change
from test_batch_admission import _git, _record, _repository

from signetum import lifecycle
from signetum.deviations import (
    DeviationClass,
    Discovered,
    ResolutionKind,
    Resolved,
    append_event,
    ledger_path,
)


def member_and_batch(tmp_path, *, historical=False):
    root = _repository(tmp_path / "repository")
    if historical:
        approve_change(root, "old")
        _git(root, "add", ".")
        _git(root, "commit", "-m", "delivered old package")
    base = _git(root, "rev-parse", "HEAD")
    member, batch = tmp_path / "member", tmp_path / "batch"
    _git(root, "worktree", "add", "-b", "impl/member", str(member), base)
    _git(root, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(member, "impl/member", base)
    _record(batch, "batch/test", base, "batch")
    _git(batch, "commit", "--allow-empty", "-m", f"open batch\n\nSignetum-Batch-Base: {base}")
    if not historical:
        approve_change(member)
        decision = member / "docs/decisions/ADP-proposal-new.md"
        decision.parent.mkdir(parents=True)
        decision.write_text("# New\n\nStatus: Accepted\n")
        _git(member, "add", ".")
        _git(member, "commit", "-m", "approve package and decision")
    (member / "behavior.txt").write_text("implemented")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "implement behavior")
    return member, batch


def discovery(member, change="example", identifier="finding"):
    return Discovered(
        id=identifier,
        change_id=change,
        member="impl/member",
        at=datetime.now(UTC),
        classification=DeviationClass.IMPLEMENTATION_CLARIFICATION,
        summary="A delivery relevant discovery.",
        original_commitment="Preserve behavior.",
        action="Retain evidence.",
        impact="Review must account for the discovery.",
    )


def resolve(member, event, *, target=None):
    append_event(
        member,
        Resolved(
            id=event.id,
            change_id=event.change_id,
            member=event.member,
            at=datetime.now(UTC),
            resolution=ResolutionKind.RESOLVED_IN_DECISION
            if target
            else ResolutionKind.NO_AUTHORITY_CHANGE,
            targets=(target,) if target else (),
            reason="Existing authority covers the implementation.",
            implemented=True,
        ),
    )


def test_pending_discovery_in_an_admitted_historical_package_refuses_final(tmp_path):
    member, batch = member_and_batch(tmp_path, historical=True)
    append_event(member, discovery(member, "old"))
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    with pytest.raises(lifecycle.AdmissionError, match="unresolved deviations: old/finding"):
        lifecycle.validate(batch, "final")


def test_admitted_historical_discovery_is_reviewed_without_reopening_approval(tmp_path):
    member, batch = member_and_batch(tmp_path, historical=True)
    event = discovery(member, "old")
    append_event(member, event)
    resolve(member, event)
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    review = lifecycle.validate(batch, "final")["delivery_review"]
    assert isinstance(review, dict)
    assert review["approvals"] == []
    assert review["reconciliation"]["changes"][0]["change_id"] == "old"
    assert review["reconciliation"]["deviation_count"] == 1


def test_numbering_projects_targets_and_preserves_original_ledger(tmp_path):
    member, batch = member_and_batch(tmp_path)
    event = discovery(member)
    append_event(member, event)
    resolve(member, event, target="docs/decisions/ADP-proposal-new.md")
    original = ledger_path(member, "example").read_bytes()
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    final = lifecycle.validate(batch, "final")
    review = final["delivery_review"]
    assert isinstance(review, dict)
    row = review["reconciliation"]["changes"][0]["deviations"][0]
    assert row["targets"] == ["docs/decisions/ADP-0001-new.md"]
    assert row["recorded_targets"] == ["docs/decisions/ADP-proposal-new.md"]
    assert ledger_path(member, "example").read_bytes() == original
    assert lifecycle.validate(batch, "final")["delivery_review"] == final["delivery_review"]


def test_new_discovery_during_checks_cannot_publish_a_stale_final_review(tmp_path, monkeypatch):
    member, batch = member_and_batch(tmp_path, historical=True)
    event = discovery(member, "old", identifier="existing")
    append_event(member, event)
    resolve(member, event)
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    original = lifecycle.execute_gate

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        append_event(member, discovery(member, "old"))
        return result

    monkeypatch.setattr(lifecycle, "execute_gate", changed)
    with pytest.raises(lifecycle.AdmissionError, match="review inputs changed"):
        lifecycle.validate(batch, "final")
    assert not list(lifecycle._receipt_root(batch).glob("final-*.json"))


def test_unrelated_pending_member_does_not_enter_batch_review(tmp_path):
    member, batch = member_and_batch(tmp_path)
    other = tmp_path / "unrelated"
    _git(member, "worktree", "add", "-b", "impl/unrelated", str(other), "HEAD")
    (other / "changes/unrelated").mkdir(parents=True)
    event = replace(discovery(other, "unrelated"), **{"member": "impl/unrelated"})
    append_event(other, event)
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    review = lifecycle.validate(batch, "final")["delivery_review"]
    assert isinstance(review, dict)
    assert review["inputs"]["members"] == ["impl/member"]
    assert review["inputs"]["changes"] == ["example"]
    assert review["reconciliation"]["deviation_count"] == 0


def test_member_receipt_changed_during_checks_refuses_review(tmp_path, monkeypatch):
    member, batch = member_and_batch(tmp_path)
    lifecycle.validate(member, "member")
    admitted = lifecycle.admit(batch, (member,))["admitted"]
    assert isinstance(admitted, list)
    receipt = lifecycle._receipt_root(member) / admitted[0]["ready_evidence"]
    original = lifecycle.execute_gate

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        receipt.write_bytes(receipt.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(lifecycle, "execute_gate", changed)
    with pytest.raises(lifecycle.AdmissionError, match="review inputs changed"):
        lifecycle.validate(batch, "final")
    assert not list(lifecycle._receipt_root(batch).glob("final-*.json"))


def test_new_discovery_after_final_refuses_remote_publication(tmp_path):
    member, batch = member_and_batch(tmp_path)
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    final = lifecycle.validate(batch, "final")
    assert isinstance(final["base"], str)
    assert isinstance(final["source"], str)
    target = tmp_path / "repository"
    remote_before = _git(target, "ls-remote", "origin", "refs/heads/main")
    append_event(member, discovery(member))
    with pytest.raises(lifecycle.AdmissionError, match="review inputs changed"):
        lifecycle.batch_deliver(batch, target, final["base"], final["source"])
    assert _git(target, "rev-parse", "HEAD") == final["base"]
    assert _git(target, "ls-remote", "origin", "refs/heads/main") == remote_before


def test_later_unadmitted_work_is_excluded_until_its_exact_tip_is_admitted(tmp_path):
    member, batch = member_and_batch(tmp_path)
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    (member / "future.txt").write_text("not admitted yet")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "later implementation")
    append_event(member, discovery(member))
    final = lifecycle.validate(batch, "final")
    review = final["delivery_review"]
    assert isinstance(review, dict)
    assert review["reconciliation"]["deviation_count"] == 0
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    with pytest.raises(lifecycle.AdmissionError, match="unresolved deviations: example/finding"):
        lifecycle.validate(batch, "final")
