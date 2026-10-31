"""Lifecycle readiness and admission consume the same approved change owner."""

import importlib
import json
import sys
from pathlib import Path

import pytest
from change_fixtures import approve_change, approve_legacy_change, consolidated_approval
from signetum import lifecycle
from signetum import lifecycle as core_lifecycle
from signetum.change_record import contract_digest, parse_change_record
from signetum.git import git_output
from signetum.serialization import contract_mapping
from signetum.workspaces import WorkspaceRecord, state_root, write_record


@pytest.fixture
def authority(request, repository, tmp_path):
    root, state = repository
    runtime = lifecycle if getattr(request, "param", "engine") == "engine" else core_lifecycle
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
        "historical-only",
        "wrong-role",
        "implemented",
        "custom-root",
    ],
)
def test_ready_requires_own_approved_change_before_checks(authority, stage):
    runtime, root, marker, scratch = authority
    if stage == "custom-root":
        path = root / "signetum.toml"
        path.write_text(path.read_text().replace('changes = "changes"', 'changes = "requests"'))
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
        if stage == "historical-only":
            approve_legacy_change(member)
        else:
            approve_change(member)
        if stage == "custom-root":
            for path in (member / "changes").rglob("*"):
                if path.is_file():
                    path.write_text(path.read_text().replace("changes/", "requests/"))
            (member / "changes").rename(member / "requests")
        elif stage == "draft":
            path = member / "changes/example/change.toml"
            path.write_text(path.read_text().split("[change.approval]")[0])
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


@pytest.mark.parametrize("authority", ["engine"], indirect=True)
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
    assert result["admitted"][0]["plan"] == ["changes/example/change.toml"]
    tip = git_output(batch, "rev-parse", "HEAD")
    message = git_output(batch, "show", "-s", "--format=%B", tip)
    assert "Signetum-Plan: changes/example/change.toml" in message
    assert "Signetum-Plan: changes/forged/" not in message


@pytest.mark.parametrize("stage", ["approved", "draft", "plan-only", "wrong-base", "dual"])
@pytest.mark.parametrize("authority", ["engine"], indirect=True)
def test_ready_uses_one_consolidated_record_without_legacy_files(authority, stage):
    runtime, root, marker, scratch = authority
    base = git_output(root, "rev-parse", "HEAD")
    member = scratch / "consolidated-member"
    branch = "plan/consolidated"
    git_output(root, "worktree", "add", "-b", branch, str(member), base)
    write_record(state_root(root), WorkspaceRecord(1, branch, base, "member"))
    consolidated_approval(
        member, "0" * 40 if stage == "wrong-base" else base, approved=stage != "draft"
    )
    if stage == "dual":
        approve_legacy_change(member)
    commit(member, "approve consolidated behavior")
    if stage != "plan-only":
        implementation(member)
    if stage == "approved":
        assert runtime.validate(member, "member")["status"] == "ready"
        assert marker.exists()
        assert not (member / "changes/example/review.toml").exists()
    else:
        with pytest.raises(runtime.AdmissionError):
            runtime.validate(member, "member")
        assert not marker.exists()


@pytest.mark.parametrize("fresh_implementation", [False, True])
def test_revised_contract_needs_its_own_post_approval_implementation(
    authority, fresh_implementation
):
    runtime, root, marker, scratch = authority
    base = git_output(root, "rev-parse", "HEAD")
    member = scratch / "reapproved-member"
    branch = "plan/reapproved"
    git_output(root, "worktree", "add", "-b", branch, str(member), base)
    write_record(state_root(root), WorkspaceRecord(1, branch, base, "member"))
    consolidated_approval(member, base)
    commit(member, "approve original outcome")
    implementation(member)
    consolidated_approval(member, base, outcome="Implement the revised outcome.")
    (member / "implementation.txt").write_text("code committed with revised approval")
    commit(member, "approve revised outcome with premature implementation")
    if fresh_implementation:
        (member / "implementation.txt").write_text("implementation after revised approval")
        commit(member, "implement revised outcome")
        assert runtime.validate(member, "member")["status"] == "ready"
        assert marker.exists()
    else:
        with pytest.raises(runtime.AdmissionError, match="plan stage"):
            runtime.validate(member, "member")
        assert not marker.exists()


@pytest.mark.parametrize("edit", ["execution", "contract", "delete"])
def test_delivered_consolidated_contract_is_protected_but_execution_can_refine(authority, edit):
    runtime, root, _, _ = authority
    module = importlib.import_module("signetum.change.scope")
    original_base = git_output(root, "rev-parse", "HEAD")
    path = consolidated_approval(root, original_base)
    commit(root, "deliver fixture approval")
    delivered = git_output(root, "rev-parse", "HEAD")
    manifest = runtime.load_manifest(root / "signetum.toml")
    assert module.delivered_plans(root, manifest, ("example",), delivered) == (
        "changes/example/change.toml",
    )
    if edit == "execution":
        path.write_text(
            path.read_text().replace(
                "Implement and validate the outcome.",
                "Use the existing runner to validate the outcome.",
            )
        )
    elif edit == "delete":
        path.unlink()
    else:
        consolidated_approval(root, original_base, outcome="A different approved outcome.")
    commit(root, "refine fixture record")
    tip = git_output(root, "rev-parse", "HEAD")
    scope = module.delivery_scope(root, manifest, delivered, tip)
    result = module.changed_commitments(root, manifest, delivered, tip, scope)
    assert result == (() if edit == "execution" else ("changes/example/change.toml",))


def test_delivery_scope_refuses_a_symlink_record_as_a_structured_error(authority):
    runtime, root, _, _ = authority
    module = importlib.import_module("signetum.change.scope")
    base = git_output(root, "rev-parse", "HEAD")
    path = consolidated_approval(root, base)
    path.rename(path.with_name("original.toml"))
    path.symlink_to("original.toml")
    commit(root, "declare a symlink instead of authority")
    manifest = runtime.load_manifest(root / "signetum.toml")
    with pytest.raises(module.ChangeError, match="regular committed file"):
        module.delivered_plans(root, manifest, ("example",), git_output(root, "rev-parse", "HEAD"))


@pytest.mark.parametrize(
    "application", ["decision", "observation", "approval-only", "tampered", "borrowed"]
)
@pytest.mark.parametrize("authority", ["engine"], indirect=True)
def test_authority_only_ready_requires_an_exact_applied_decision(authority, application):
    runtime, root, marker, scratch = authority
    base = git_output(root, "rev-parse", "HEAD")
    member = scratch / "decision-member"
    branch = "plan/decision-member"
    git_output(root, "worktree", "add", "-b", branch, str(member), base)
    write_record(state_root(root), WorkspaceRecord(1, branch, base, "member"))
    path = consolidated_approval(member, base)
    proposal = (
        '{id="example/initial",change_id="example",'
        'authority="changes/example/change.toml#decisions/example/initial",'
        'reason="Retain the accepted boundary.",topics=[{expected_version=0,'
        'revision={id="validation",version=1,'
        'summary="Validation does not authorize delivery."}}]}'
    )
    source = path.read_text().split("[change.approval]")[0]
    source = source.replace(
        "[change.contract]\n", "[change.contract]\ndecisions=[" + proposal + "]\n"
    )
    digest = contract_digest(parse_change_record(source).contract)
    source += f'''[change.approval]
actor = "Owner"
recorded_at = 2026-10-29
source = "Owner confirmed the exact decision fixture."
contract_digest = "{digest}"
'''
    path.write_text(source)
    commit(member, "approve exact decision")
    module = importlib.import_module("signetum.development_store")
    decision = parse_change_record(source).contract.decisions[0]
    request: dict[str, object] = dict(
        id="example/apply",
        change_id="example",
        approval_digest=digest,
        operation="reconcile",
        reason="Apply the exact approved decision.",
    )
    if application in {"decision", "tampered", "borrowed"}:
        request["decisions"] = [contract_mapping(decision)]
    elif application == "observation":
        request["observations"] = [
            dict(
                id="example/note",
                requirements=["REQ-1"],
                summary="Inspection completed.",
                reason="Keep the finding.",
            )
        ]
    if application != "approval-only":
        module.append_transaction(
            member,
            module.parse_request(request),
            expected_history=module.snapshot(member).history_digest,
        )
        if application == "tampered":
            journal = member / "changes/example/events.jsonl"
            journal.write_text(
                journal.read_text().replace(
                    "Validation does not authorize delivery.", "Publication is automatic."
                )
            )
        if application == "borrowed":
            git_output(member, "switch", "-c", "side/decision")
        commit(member, "apply approved authority without unrelated code")
        if application == "borrowed":
            git_output(member, "switch", branch)
            git_output(member, "merge", "--no-ff", "side/decision", "-m", "borrow decision")
            observation = dict(
                id="example/after-merge",
                change_id="example",
                approval_digest=digest,
                operation="record",
                reason="An ordinary note is not own decision application.",
                observations=[
                    dict(
                        id="example/note",
                        requirements=["REQ-1"],
                        summary="Review the merged decision.",
                        reason="Keep context.",
                    )
                ],
            )
            module.append_transaction(
                member,
                module.parse_request(observation),
                expected_history=module.snapshot(member).history_digest,
            )
            commit(member, "append ordinary observation after borrowed application")
    if application == "decision":
        assert runtime.validate(member, "member")["status"] == "ready"
        assert marker.exists()
    else:
        with pytest.raises(runtime.AdmissionError):
            runtime.validate(member, "member")
        assert not marker.exists()
