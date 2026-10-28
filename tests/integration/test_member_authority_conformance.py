"""Lifecycle readiness and admission consume the same approved change owner."""

import json
import sys
from pathlib import Path

import pytest
from change_fixtures import approve_change
from test_lifecycle_conformance import _template_lifecycle

from signetum import lifecycle
from signetum.git import git_output
from signetum.workspaces import WorkspaceRecord, state_root, write_record


@pytest.fixture(params=["engine", "template"])
def authority(request, repository, tmp_path):
    root, state = repository
    runtime = lifecycle if request.param == "engine" else _template_lifecycle()
    marker = state / "checks"
    path = root / "signetum.toml"
    command = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"]
    path.write_text(path.read_text().replace('["true"]', json.dumps(command)))
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare observed member check")
    return runtime, root, marker, tmp_path


def commit(root, message):
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", message)


def implementation(member):
    (member / "implementation.txt").write_text("own implementation")
    commit(member, "implement approved behavior")


@pytest.mark.parametrize(
    "stage",
    [
        "missing",
        "draft",
        "plan-only",
        "before-approval",
        "wrong-role",
        "decision",
        "implemented",
        "custom-root",
    ],
)
def test_ready_requires_own_approved_change_before_checks(authority, stage):
    runtime, root, marker, scratch = authority
    if stage == "custom-root":
        path = root / "signetum.toml"
        path.write_text(path.read_text().replace("changes/*", "requests/*"))
        commit(root, "declare custom change root")
    base = git_output(root, "rev-parse", "HEAD")
    member = scratch / "member"
    branch = "plan/member-authority"
    git_output(root, "worktree", "add", "-b", branch, str(member), base)
    write_record(
        state_root(root),
        WorkspaceRecord(1, branch, base, "batch" if stage == "wrong-role" else "member"),
    )
    if stage == "before-approval":
        implementation(member)
    if stage != "missing":
        approve_change(member)
        if stage == "custom-root":
            for path in (member / "changes").rglob("*"):
                if path.is_file():
                    path.write_text(path.read_text().replace("changes/", "requests/"))
            (member / "changes").rename(member / "requests")
        elif stage == "draft":
            path = member / "changes/example/specs/behavior.toml"
            path.write_text(
                path.read_text()
                .replace('status = "approved"', 'status = "draft"')
                .replace("implementation_authorized = true", "implementation_authorized = false")
            )
        elif stage == "decision":
            decision = member / "docs/decisions/ADP-pending.md"
            decision.parent.mkdir(parents=True)
            decision.write_text(
                "# Pending\nStatus: Proposed\nSupersedes: None\nSuperseded by: None\n"
            )
            path = member / "changes/example/specs/behavior.toml"
            path.write_text(
                path.read_text().replace(
                    "plan = ", 'decisions = ["docs/decisions/ADP-pending.md"]\nplan = '
                )
            )
        commit(member, "declare approval package")
    if stage not in {"plan-only", "before-approval"}:
        implementation(member)
    if stage in {"implemented", "custom-root"}:
        result = runtime.validate(member, "member")
        assert result["status"] == "ready"
        assert marker.exists()
        assert Path(result["receipt"]).is_file()
    else:
        with pytest.raises(runtime.AdmissionError):
            runtime.validate(member, "member")
        assert not marker.exists(), "refused authority must not start checks"
        assert not list((state_root(root) / "validation").glob("member-*.json"))


def test_ready_cannot_claim_a_change_owned_by_another_member(authority):
    runtime, root, marker, scratch = authority
    base = git_output(root, "rev-parse", "HEAD")
    member = scratch / "first"
    git_output(root, "worktree", "add", "-b", "plan/first", str(member), base)
    write_record(state_root(root), WorkspaceRecord(1, "plan/first", base, "member"))
    approve_change(member)
    commit(member, "approve change")
    implementation(member)
    runtime.validate(member, "member")
    marker.unlink()
    second = scratch / "second"
    git_output(root, "worktree", "add", "-b", "plan/second", str(second), "plan/first")
    write_record(state_root(root), WorkspaceRecord(1, "plan/second", base, "member"))
    with pytest.raises(runtime.AdmissionError, match="already belongs"):
        runtime.validate(second, "member")
    assert not marker.exists()


def test_admission_uses_committed_package_plans_and_ignores_forged_trailer(authority):
    runtime, root, _, scratch = authority
    base = git_output(root, "rev-parse", "HEAD")
    member, batch = scratch / "member", scratch / "batch"
    git_output(root, "worktree", "add", "-b", "plan/admission", str(member), base)
    write_record(state_root(root), WorkspaceRecord(1, "plan/admission", base, "member"))
    approve_change(member)
    commit(member, "approve package")
    implementation(member)
    git_output(
        member, "commit", "--amend", "-m", "implement\n\nDelivers: changes/forged/plans/fake.md"
    )
    runtime.validate(member, "member")
    git_output(root, "worktree", "add", "-b", "batch/admission", str(batch), base)
    write_record(state_root(root), WorkspaceRecord(1, "batch/admission", base, "batch"))
    result = runtime.admit(batch, (member,))
    assert result["admitted"][0]["plan"] == ["changes/example/plans/behavior.md"]
    tip = git_output(batch, "rev-parse", "HEAD")
    message = git_output(batch, "show", "-s", "--format=%B", tip)
    assert "Signetum-Plan: changes/example/plans/behavior.md" in message
    assert "Signetum-Plan: changes/forged/" not in message
