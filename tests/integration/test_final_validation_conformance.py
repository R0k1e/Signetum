"""Native final validation preserves scope and evidence bindings in the engine."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from change_fixtures import append_historical_event as append_event
from change_fixtures import approve_legacy_change as approve_change
from change_fixtures import commit_approval
from signetum import lifecycle, workspace_operations
from signetum.deviations import DeviationClass, Discovered
from signetum.git import git_output


@pytest.fixture
def final_runtime(request):
    return lifecycle


def assembled(repository, *, historical=False, rewrite=False, pending=False):
    root, _ = repository
    if historical:
        approve_change(root, "old")
        git_output(root, "add", ".")
        git_output(root, "commit", "-m", "deliver earlier approval")
        git_output(root, "push", "origin", "main")
    base = git_output(root, "rev-parse", "HEAD")
    member = Path(str(workspace_operations.workspace_open(root, "plan/current", base)["worktree"]))
    commit_approval(member, "current")
    if historical:
        path = member / ("changes/old/review.toml" if rewrite else "changes/old/plans/behavior.md")
        path.write_text(path.read_text() + "\n# Historical edit\n")
    (member / "implementation.txt").write_text("current implementation")
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "implement change without a Plan trailer")
    lifecycle.validate(member, "member")
    if pending:
        append_event(
            member,
            Discovered(
                id="pending",
                change_id="current",
                member="plan/current",
                at=datetime.now(UTC),
                summary="Delivery-relevant discovery",
                classification=DeviationClass.SAFE_SUPPORTING_CHANGE,
                original_commitment="Keep behavior",
                action="Reuse shared owner",
                impact="No behavior change",
            ),
        )
    batch = Path(
        str(workspace_operations.open_workspace(root, "batch/test", base, kind="batch")["worktree"])
    )
    admitted = lifecycle.admit(batch, (member,))["admitted"]
    return member, batch, admitted


def test_final_reviews_first_delivered_change_and_lists_historical_plan_edit(
    repository, final_runtime
):
    _, batch, _ = assembled(repository, historical=True)
    archive = batch / "changes/archived-yaml"
    (archive / "plans").mkdir(parents=True)
    (archive / "review.yaml").write_text("review:\n  status: historical\n")
    (archive / "plans/original.md").write_text("# Retained original rationale\n")
    git_output(batch, "add", ".")
    git_output(batch, "commit", "-m", "retain raw historical documents")
    result = final_runtime.validate(batch, "final")
    review = result["delivery_review"]
    assert [item["change_id"] for item in review["approvals"]] == ["current"]
    assert review["previously_delivered"] == [
        {"change_id": "old", "paths": ["changes/old/plans/behavior.md"]}
    ]
    assert len(review["inputs"]["member_evidence"]) == 1


def test_final_refuses_rewriting_delivered_commitments(repository, final_runtime):
    _, batch, _ = assembled(repository, historical=True, rewrite=True)
    with pytest.raises(final_runtime.AdmissionError, match="rewrites delivered commitments"):
        final_runtime.validate(batch, "final")
    assert not list(final_runtime._receipt_root(batch).glob("final-*.json"))


def test_final_refuses_an_unresolved_admitted_discovery(repository, final_runtime):
    _, batch, _ = assembled(repository, pending=True)
    with pytest.raises(final_runtime.AdmissionError, match="unresolved deviations"):
        final_runtime.validate(batch, "final")
    assert not list(final_runtime._receipt_root(batch).glob("final-*.json"))


def test_final_cannot_publish_if_admitted_receipt_changes_during_checks(
    repository, final_runtime, monkeypatch
):
    _, batch, admitted = assembled(repository)
    path = final_runtime._receipt_root(batch) / admitted[0]["ready_evidence"]
    original = final_runtime.execute_gate

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(final_runtime, "execute_gate", changed)
    with pytest.raises(final_runtime.AdmissionError, match="review inputs changed"):
        final_runtime.validate(batch, "final")
    assert not list(final_runtime._receipt_root(batch).glob("final-*.json"))
