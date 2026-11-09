"""Real Git scenarios for supported workspace recovery and removal."""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from change_fixtures import approve_change, commit_approval
from signetum import lifecycle, maintenance, runtime_identity
from signetum import workspace_operations as ops
from signetum import worktrunk as wt
from signetum.commit_check import CHAIN, commit_check_status, install_commit_check
from signetum.development_store import snapshot
from signetum.git import git_output, run_git
from signetum.operations import AdmissionError, InfrastructureError, MergeConflict, OperationFailed
from signetum.runtime_identity import engine_source as actual_engine_source
from signetum.synchronization import member_contribution_paths
from signetum.workflow_status import workflow_status
from signetum.workspaces import (
    BatchEngine,
    branch_name,
    exclude_workspaces,
    read_record,
    state_root,
    workspace_destination,
)
from signetum.worktrunk import run_tool as actual_run_tool


def opened(repository, branch):
    result = ops.workspace_open(repository, branch, git_output(repository, "rev-parse", "HEAD"))
    path = result["worktree"]
    assert isinstance(path, str)
    return Path(path)


def preparation_command(repository, command):
    path = repository / "signetum.toml"
    manifest = lifecycle.load_manifest(path)
    previous = next(
        shard.command for shard in manifest.validation.shards if shard.name == "test:prepare"
    )
    path.write_text(path.read_text().replace(json.dumps(list(previous)), json.dumps(command)))


def test_ready_fails_when_prepare_needs_an_ignored_file_missing_from_the_commit(repository):
    root, _state = repository
    member = opened(root, "plan/example")
    commit_approval(member)
    preparation_command(
        member,
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; "
            "sys.exit(0 if Path('local.secret').is_file() else 13)",
        ],
    )
    (member / ".gitignore").write_text("local.secret\n")
    git_output(member, "add", "signetum.toml", ".gitignore")
    git_output(member, "commit", "-m", "require an ignored preparation input")
    (member / "local.secret").write_text("only in the editing worktree\n")

    with pytest.raises(InfrastructureError, match="13"):
        lifecycle.validate(member, "member")

    assert (member / "local.secret").read_text() == "only in the editing worktree\n"
    assert "signetum-ready" not in git_output(root, "worktree", "list", "--porcelain")


def test_ready_reports_approval_source_when_ignored_files_are_unnecessary(repository):
    root, _state = repository
    member = opened(root, "plan/example")
    commit_approval(member)
    commit_file(member, ".gitignore", ".venv/\n")
    commit_file(member, "implementation.txt")
    (member / ".venv").mkdir()
    (member / ".venv" / "pyvenv.cfg").write_text("home = fixture\n")

    result = lifecycle.validate(member, "member")

    assert result["status"] == "ready"
    approvals = result["approvals"]
    assert isinstance(approvals, list)
    assert approvals[0]["actor"] == "Owner"
    assert approvals[0]["recorded_at"] == "2026-10-29"
    assert approvals[0]["source"] == "Owner confirmed the fixture outcome."
    assert str(approvals[0]["contract_digest"]).startswith("sha256:")
    assert (member / ".venv" / "pyvenv.cfg").is_file()
    assert "signetum-ready" not in git_output(root, "worktree", "list", "--porcelain")


def test_batch_deliver_rejects_a_missing_path_before_git(repository, tmp_path):
    root, _state = repository
    missing = tmp_path / "main"
    with pytest.raises(AdmissionError, match="branch name is not a path") as failure:
        lifecycle.batch_deliver(missing, root, "a" * 40, "b" * 40)
    assert "cannot change to" not in str(failure.value)


def test_batch_deliver_lets_git_refuse_an_existing_non_repository(repository, tmp_path):
    root, _state = repository
    empty = tmp_path / "main"
    empty.mkdir()
    with pytest.raises(AdmissionError, match="not a git repository") as failure:
        lifecycle.batch_deliver(empty, root, "a" * 40, "b" * 40)
    assert "branch name is not a path" not in str(failure.value)


def test_batch_deliver_help_names_directories_and_full_commits():
    parser = lifecycle._parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    text = " ".join(subparsers.choices["batch-deliver"].format_help().split())
    assert "worktree directory" in text
    assert "branch name is not a path" in text
    assert "Full commit of the expected batch base." in text
    assert "Full commit of the reviewed batch tip." in text


def test_open_never_adopts_the_delivery_workspace(repository):
    root, state = repository
    before = git_output(root, "worktree", "list", "--porcelain")
    with pytest.raises(AdmissionError, match="delivery worktree"):
        ops.workspace_open(root, "main", "HEAD")
    assert git_output(root, "worktree", "list", "--porcelain") == before
    assert not (state / "attempts").exists()


def test_open_refuses_ambiguous_registered_branch_without_preparing(repository):
    root, state = repository
    member = opened(root, "plan/duplicate")
    duplicate = root.parent / "duplicate"
    git_output(root, "worktree", "add", "--force", str(duplicate), "plan/duplicate")
    with pytest.raises(AdmissionError, match="registered more than once"):
        ops.workspace_open(root, "plan/duplicate", "HEAD")
    assert (state / "attempts").read_text() == "1"
    assert member.exists() and duplicate.exists()


def test_open_recovers_creation_interruption_only_at_the_exact_base(repository):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    exclude_workspaces(root)
    member = workspace_destination(root, "plan/recover-create")
    assert member.parent == root / ".worktrees"
    assert "%" not in member.name
    assert member != workspace_destination(root, "plan%2Frecover-create")
    member.parent.mkdir(parents=True, exist_ok=True)
    git_output(root, "worktree", "add", "-b", "plan/recover-create", str(member), base)
    result = ops.workspace_open(root, "plan/recover-create", base)
    assert result["resumed"] is True
    assert read_record(state_root(root), "plan/recover-create").base == base
    assert git_output(member, "rev-parse", "HEAD") == base


def test_prepare_requires_a_declared_gate(repository):
    root, _ = repository
    member = opened(root, "plan/no-prepare")
    manifest = member / "signetum.toml"
    commit_file(
        member,
        "signetum.toml",
        manifest.read_text().replace(
            '[[validation.gates]]\nname = "prepare"\nshards = ["test:prepare"]\n', ""
        ),
    )
    with pytest.raises(AdmissionError, match="declare a prepare gate"):
        ops.worktree_prepare(member)


@pytest.mark.parametrize("path", ["seed.txt", "untracked.txt"])
def test_merge_preparation_refuses_unstaged_work(repository, path):
    root, state = repository
    member = opened(root, "plan/unstaged-prepare")
    (member / path).write_text("retain me")
    with pytest.raises(AdmissionError, match="all merge resolutions staged"):
        ops.worktree_prepare(member, allow_merge=True)
    assert (member / path).read_text() == "retain me"
    assert (state / "attempts").read_text() == "1"


@pytest.mark.parametrize("stage", [False, True])
def test_preparation_cannot_rewrite_a_staged_resolution(repository, stage, capsys):
    root, _ = repository
    member = opened(root, "plan/changed-resolution")
    script = (
        "from pathlib import Path; import sys, subprocess; "
        "Path('seed.txt').write_text('tool modification'); "
        "print('tool stdout'); print('tool stderr', file=sys.stderr)"
    )
    if stage:
        script += "; subprocess.run(['git', 'add', 'seed.txt'], check=True)"
    preparation_command(member, [sys.executable, "-c", script])
    (member / "seed.txt").write_text("staged resolution")
    git_output(member, "add", ".")
    before = git_output(member, "rev-parse", "HEAD")
    with pytest.raises(OperationFailed, match="changed the staged merge"):
        ops.worktree_prepare(member, allow_merge=True)
    assert git_output(member, "rev-parse", "HEAD") == before
    assert (member / "seed.txt").read_text() == "tool modification"
    output = capsys.readouterr().err
    assert "tool stdout" in output and "tool stderr" in output


def test_preparation_cannot_advance_the_committed_source(repository):
    root, _ = repository
    member = opened(root, "plan/changed-head")
    base = lifecycle._recorded_base(member)
    preparation_command(member, ["git", "commit", "--allow-empty", "-m", "tool changed HEAD"])
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "declare tool behavior")
    before = git_output(member, "rev-parse", "HEAD")
    with pytest.raises(OperationFailed, match="committed source identity"):
        ops.worktree_prepare(member)
    assert git_output(member, "rev-parse", "HEAD") != before
    assert lifecycle._recorded_base(member) == base


@pytest.mark.parametrize("selector", [{}, {"all_delivered": True, "branch": "main"}])
def test_cleanup_refuses_ambiguous_scope_before_contacting_remote(repository, selector):
    root, _ = repository
    git_output(root, "remote", "remove", "origin")
    before = git_output(root, "worktree", "list", "--porcelain")
    with pytest.raises(AdmissionError, match="select one worktree"):
        ops.cleanup(root, **selector)
    assert git_output(root, "worktree", "list", "--porcelain") == before


@pytest.mark.parametrize("foreign_repository", [False, True])
def test_sync_refuses_a_source_without_same_repository_batch_authority(
    repository, foreign_repository
):
    root, _ = repository
    member = opened(root, "plan/sync-receiver")
    if foreign_repository:
        source = root.parent / "foreign"
        source.mkdir()
        git_output(source, "init")
        expected = "same repository"
    else:
        source = opened(root, "plan/not-a-batch")
        expected = "verified batch provenance"
    before = git_output(member, "rev-parse", "HEAD")
    with pytest.raises(AdmissionError, match=expected):
        ops.workspace_sync(member, source)
    assert git_output(member, "rev-parse", "HEAD") == before


def commit_file(repository, name, value="work"):
    (repository / name).write_text(value)
    git_output(repository, "add", name)
    git_output(repository, "commit", "-m", f"implement {name}")
    return git_output(repository, "rev-parse", "HEAD")


def publish_member(repository, member):
    git_output(repository, "merge", "--no-ff", branch_name(member), "-m", "deliver fixture")
    git_output(repository, "push", "origin", "main")


def land(repository, *commits):
    # Diverge first: a cherry-pick onto the unchanged parent recreates the same commit.
    commit_file(repository, "delivery.txt", "delivered independently")
    git_output(repository, "cherry-pick", *commits)
    git_output(repository, "push", "origin", "main")


def removed_outcomes(removed):
    assert isinstance(removed, list)
    for row in removed:
        retirement = json.loads(Path(row["retirement"]).read_text())
        assert retirement["branch"] == row["branch"] and retirement["tip"] == row["tip"]
        assert retirement["outcome"] == row["outcome"]
        assert not Path(row["worktree"]).exists()
        primary = Path(row["worktree"]).parents[1]
        assert run_git(primary, "rev-parse", "--verify", f"refs/heads/{row['branch']}").returncode
    return {row["branch"]: row["outcome"] for row in removed}


@pytest.mark.parametrize("fails", [False, True])
def test_changed_explains_selected_checks_without_executing_or_granting_readiness(
    repository, fails
):
    root, state = repository
    marker = state / "diagnostic-ran"
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).touch(); "
        "sys.exit(int(sys.argv[2]))",
        str(marker),
        str(int(fails)),
    ]
    manifest = root / "signetum.toml"
    manifest.write_text(manifest.read_text().replace('["true"]', json.dumps(command)))
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare observable diagnostic")
    member = opened(root, "plan/diagnostic")
    tip = commit_file(member, "implementation.txt")
    result = lifecycle.explain_ready(member)
    assert result["status"] == "selection-only"
    assert result["executed"] == []
    assert not marker.exists()
    assert git_output(member, "rev-parse", "HEAD") == tip
    assert not (state_root(member) / "validation").exists()


@pytest.mark.parametrize("path", ["seed.txt", "untracked.txt"])
def test_changed_refuses_dirty_files_before_running_checks(repository, path):
    root, _ = repository
    member = opened(root, "plan/dirty-diagnostic")
    commit_file(member, "implementation.txt")
    (member / path).write_text("not selected by committed diff")
    with pytest.raises(AdmissionError, match="not clean"):
        lifecycle.explain_ready(member)


def test_changed_refuses_workspace_without_committed_contribution(repository):
    root, _ = repository
    member = opened(root, "plan/no-contribution")
    with pytest.raises(AdmissionError, match="no committed contribution"):
        lifecycle.explain_ready(member)


def test_changed_without_provider_plans_full_checks_for_unexplained_paths(repository):
    root, _ = repository
    manifest = root / "signetum.toml"
    commit_file(
        root, "signetum.toml", manifest.read_text().replace('paths = ["**"]', 'paths = ["src/**"]')
    )
    member = opened(root, "plan/no-selection")
    commit_file(member, "unexplained.md")
    result = lifecycle.explain_ready(member)
    assert result["status"] == "selection-only"
    assert result["executed"] == []
    assert result["requires_final"] is True


def test_changed_selection_only_does_not_execute_the_selected_command(
    repository, monkeypatch, capsys
):
    root, _ = repository
    manifest = root / "signetum.toml"
    commit_file(root, "signetum.toml", manifest.read_text().replace('["true"]', '["false"]'))
    member = opened(root, "plan/selection-only")
    commit_file(member, "implementation.txt")
    result = lifecycle.explain_ready(member)
    assert result["status"] == "selection-only"
    assert result["executed"] == []
    assert result["shards"] == ("test:check",)
    monkeypatch.chdir(member)
    assert lifecycle.main(["ready", "--explain"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["outcome"] == "selection-only"
    assert document["checks_started"] is False


def test_failed_preparation_keeps_base_and_same_workspace_can_retry(repository):
    root, state = repository
    base = git_output(root, "rev-parse", "HEAD")
    (state / "fail").touch()
    with pytest.raises(InfrastructureError, match="preparation exited"):
        ops.workspace_open(root, "plan/example", base)
    member = wt.registered_workspace(root, "plan/example").path
    assert read_record(state_root(member), "plan/example").base == base
    assert git_output(member, "rev-parse", "HEAD") == base
    (state / "fail").unlink()
    result = ops.workspace_open(root, "plan/example", base)
    assert result["resumed"] is True
    assert result["worktree"] == str(member)
    assert (state / "attempts").read_text() == "2"


def test_open_refuses_replacing_an_existing_base(repository):
    root, _ = repository
    member = opened(root, "plan/example")
    base = git_output(member, "rev-parse", "HEAD")
    other = commit_file(root, "later.txt")
    with pytest.raises(AdmissionError, match="different recorded base"):
        ops.workspace_open(root, "plan/example", other)
    assert read_record(state_root(member), "plan/example").base == base


def test_delivery_sync_preserves_member_base_and_does_not_prepare(repository):
    root, state = repository
    member = opened(root, "plan/example")
    base = read_record(state_root(member), "plan/example").base
    commit_file(member, "own.txt")
    source = commit_file(root, "sibling.txt")
    git_output(root, "push", "origin", "main")
    attempts = (state / "attempts").read_text()
    result = ops.workspace_sync(member)
    assert result["source"] == source
    assert read_record(state_root(member), "plan/example").base == base
    assert (member / "sibling.txt").read_text() == "work"
    assert git_output(member, "show", "-s", "--format=%P", "HEAD").split()[1] == source
    assert (state / "attempts").read_text() == attempts


def test_unadmitted_member_can_sync_verified_batch(repository):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    sibling = opened(root, "plan/sibling")
    commit_approval(sibling, "sibling")
    commit_file(sibling, "sibling.txt")
    lifecycle.validate(sibling, "member")
    batch = Path(str(ops.open_workspace(root, "batch/test", base, kind="batch")["worktree"]))
    lifecycle.admit(batch, (sibling,))
    member = opened(root, "plan/dependent")
    result = ops.workspace_sync(member, batch)
    assert result["source"] == git_output(batch, "rev-parse", "HEAD")
    assert git_output(member, "show", "-s", "--format=%s", "HEAD") == (
        "Merge batch/test into plan/dependent"
    )
    assert (member / "sibling.txt").is_file()
    assert read_record(state_root(member), "plan/dependent").base == base


def test_sync_conflict_keeps_git_state_and_names_member_recovery(repository):
    root, _ = repository
    member = opened(root, "plan/example")
    commit_file(member, "seed.txt", "member\n")
    commit_file(root, "seed.txt", "delivery\n")
    git_output(root, "push", "origin", "main")
    with pytest.raises(MergeConflict) as refusal:
        ops.workspace_sync(member)
    assert "git commit --no-edit" in refusal.value.expected
    assert run_git(member, "rev-parse", "--verify", "MERGE_HEAD").returncode == 0


def conflicted_sync(repository, branch):
    root, _ = repository
    member = opened(root, branch)
    base = read_record(state_root(member), branch).base
    commit_file(member, "seed.txt", "member\n")
    commit_file(root, "seed.txt", "delivery\n")
    commit_file(root, "delivered.txt")
    git_output(root, "push", "origin", "main")
    with pytest.raises(MergeConflict):
        ops.workspace_sync(member)
    (member / "seed.txt").write_text("resolved\n")
    git_output(member, "add", "seed.txt")
    return member, base


def test_conflicted_sync_committed_without_editing_is_verified(repository):
    member, base = conflicted_sync(repository, "plan/no-edit")
    git_output(member, "commit", "--no-edit")
    owned = member_contribution_paths(member, base, git_output(member, "rev-parse", "HEAD"))
    assert set(owned) == {"seed.txt"}


def test_rerunning_sync_recognizes_a_recorded_merge_that_lost_its_trailer(repository):
    member, base = conflicted_sync(repository, "plan/lost-trailer")
    git_output(member, "commit", "-m", "resolve the sync conflict")
    tip = git_output(member, "rev-parse", "HEAD")
    assert "delivered.txt" in member_contribution_paths(member, base, tip)
    result = ops.workspace_sync(member)
    assert result["status"] == "recognized"
    assert result["merge"] == tip
    assert git_output(member, "rev-parse", "HEAD") == tip
    assert set(member_contribution_paths(member, base, tip)) == {"seed.txt"}
    assert ops.workspace_sync(member)["status"] != "recognized"


def test_rerunning_sync_does_not_recognize_a_manual_merge(repository):
    root, _ = repository
    member = opened(root, "plan/manual")
    base = read_record(state_root(member), "plan/manual").base
    commit_file(member, "own.txt")
    commit_file(root, "delivered.txt")
    git_output(root, "push", "origin", "main")
    git_output(member, "fetch", "origin", "main")
    git_output(member, "merge", "--no-ff", "FETCH_HEAD", "-m", "manual merge")
    assert ops.workspace_sync(member)["status"] != "recognized"
    tip = git_output(member, "rev-parse", "HEAD")
    assert "delivered.txt" in member_contribution_paths(member, base, tip)


def test_cleanup_preserves_protected_fresh_dirty_and_unmerged_workspaces(repository):
    root, _ = repository
    delivered = opened(root, "plan/delivered")
    commit_file(delivered, "delivered.txt")
    publish_member(root, delivered)
    dirty = opened(root, "plan/dirty")
    commit_file(dirty, "dirty.txt")
    publish_member(root, dirty)
    (dirty / "untracked.txt").write_text("keep")
    advanced = opened(root, "plan/advanced")
    commit_file(advanced, "advanced.txt")
    fresh = opened(root, "plan/fresh")
    result = ops.cleanup(root, all_delivered=True)
    assert removed_outcomes(result["removed"]) == {"plan/delivered": "delivered"}
    retained = result["retained"]
    assert isinstance(retained, list)
    reasons = {row["branch"]: row["reason"] for row in retained}
    assert reasons == {
        "plan/dirty": "dirty",
        "plan/advanced": "not_contained",
        "plan/fresh": "fresh_workspace",
    }
    assert all(path.exists() for path in (root, dirty, advanced, fresh))


@pytest.mark.parametrize("staged", [False, True])
def test_explicit_discard_never_discards_staged_work(repository, staged):
    root, _ = repository
    member = opened(root, "plan/discard")
    commit_file(member, "own.txt")
    publish_member(root, member)
    (member / "own.txt").write_text("uncommitted")
    if staged:
        git_output(member, "add", "own.txt")
    result = ops.cleanup(root, worktree=member, discard=True)
    if staged:
        retained = result["retained"]
        assert isinstance(retained, list)
        assert retained[0]["reason"] == "staged"
        assert member.exists()
    else:
        assert removed_outcomes(result["removed"]) == {"plan/discard": "delivered"}
        assert not member.exists()


def test_explicit_protection_retains_even_delivered_residue(repository):
    root, _ = repository
    member = opened(root, "plan/protected")
    commit_file(member, "own.txt")
    publish_member(root, member)
    result = ops.cleanup(root, worktree=member, protected_worktrees=(member,))
    retained = result["retained"]
    assert isinstance(retained, list)
    assert retained[0]["reason"] == "protected"
    assert member.exists()


def test_sync_does_not_claim_siblings_package_or_charge_its_unchanged_paths(repository):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    sibling = opened(root, "plan/sibling")
    approve_change(sibling, "sibling")
    git_output(sibling, "add", ".")
    git_output(sibling, "commit", "-m", "approve sibling")
    commit_file(sibling, "sibling.txt")
    lifecycle.validate(sibling, "member")
    batch = Path(str(ops.open_workspace(root, "batch/test", base, kind="batch")["worktree"]))
    lifecycle.admit(batch, (sibling,))
    member = opened(root, "plan/dependent")
    approve_change(member, "dependent")
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "approve dependent")
    commit_file(member, "own.txt")
    ops.workspace_sync(member, batch)
    result = lifecycle.validate(member, "member")
    assert result["status"] == "ready"
    changed = lifecycle.explain_ready(member)["files"]
    assert isinstance(changed, tuple)
    assert set(changed) == {
        "own.txt",
        "changes/dependent/change.toml",
    }


def test_batch_continuation_validates_staged_repair_before_committing(repository):
    root, _ = repository
    manifest = root / "signetum.toml"
    check = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; "
        "sys.exit(1 if Path('seed.txt').read_text() == 'bad' else 0)",
    ]
    manifest.write_text(
        manifest.read_text().replace('command = ["true"]', "command = " + json.dumps(check))
    )
    git_output(root, "commit", "-am", "declare observable resolution contract")
    base = git_output(root, "rev-parse", "HEAD")
    left, right = opened(root, "plan/left"), opened(root, "plan/right")
    commit_approval(left, "left")
    commit_approval(right, "right")
    commit_file(left, "seed.txt", "left")
    commit_file(right, "seed.txt", "right")
    lifecycle.validate(left, "member")
    lifecycle.validate(right, "member")
    batch = Path(str(ops.open_workspace(root, "batch/test", base, kind="batch")["worktree"]))
    lifecycle.admit(batch, (left,))
    with pytest.raises(MergeConflict):
        lifecycle.admit(batch, (right,))
    before = git_output(batch, "rev-parse", "HEAD")
    (batch / "seed.txt").write_text("bad")
    git_output(batch, "add", "seed.txt")
    with pytest.raises(lifecycle.ValidationExecutionError):
        lifecycle.continue_batch(batch)
    assert git_output(batch, "rev-parse", "HEAD") == before
    assert run_git(batch, "rev-parse", "--verify", "MERGE_HEAD").returncode == 0
    (batch / "seed.txt").write_text("good")
    git_output(batch, "add", "seed.txt")
    result = lifecycle.continue_batch(batch)
    assert result["batch_commit"] == git_output(batch, "rev-parse", "HEAD")
    assert (batch / "seed.txt").read_text() == "good"
    assert run_git(batch, "rev-parse", "--verify", "MERGE_HEAD").returncode != 0


def test_failed_admission_preparation_keeps_merge_for_supported_retry(repository):
    root, state = repository
    base = git_output(root, "rev-parse", "HEAD")
    member = opened(root, "plan/example")
    commit_approval(member, "example")
    commit_file(member, "own.txt")
    lifecycle.validate(member, "member")
    batch = Path(str(ops.open_workspace(root, "batch/test", base, kind="batch")["worktree"]))
    (state / "fail").touch()
    with pytest.raises(InfrastructureError) as refusal:
        lifecycle.admit(batch, (member,))
    assert "batch-admit" in refusal.value.expected
    assert "--batch" in refusal.value.expected
    assert str(batch) in refusal.value.expected
    merged = git_output(batch, "rev-parse", "HEAD")
    assert (batch / "own.txt").is_file()
    (state / "fail").unlink()
    retried = lifecycle.admit(batch, (member,))
    assert git_output(batch, "rev-parse", "HEAD") == merged
    assert retried["admitted"] == []
    unchanged = retried["unchanged"]
    assert isinstance(unchanged, list)
    assert unchanged[0]["original"] == git_output(member, "rev-parse", "HEAD")


def test_validated_delivery_keeps_active_runtime_until_cleanup_from_another_checkout(
    repository, monkeypatch
):
    root, _ = repository
    monkeypatch.setattr(ops, "install_commit_check", install_commit_check)
    base = git_output(root, "rev-parse", "HEAD")
    member = opened(root, "plan/example")
    commit_approval(member, "example")
    commit_file(member, "own.txt")
    lifecycle.validate(member, "member")
    opened_batch = lifecycle.batch_open(
        root, (member,), actor="Owner", source="Owner authorized the fixture batch"
    )
    batch = Path(str(opened_batch["worktree"]))
    assert git_output(batch, "symbolic-ref", "--short", "HEAD") == "batch/example"
    assert not (batch / "changes/batch-example").exists()
    authorization = read_record(state_root(batch), "batch/example").authorization
    assert git_output(batch, "status", "--porcelain") == ""
    assert opened_batch["commit_check"] == {
        "status": "active",
        "hook": str(root / ".git/hooks/reference-transaction"),
    }
    retried = lifecycle.batch_open(
        root, (member,), actor="Owner", source="Owner authorized the fixture batch"
    )
    assert retried["worktree"] == str(batch)
    assert read_record(state_root(batch), "batch/example").authorization == authorization
    commit_file(batch, "combination.txt")
    final = lifecycle.validate(batch, "final")
    tip = final["source"]
    assert isinstance(tip, str)
    with monkeypatch.context() as context:
        context.setattr(ops, "__file__", str(member / "active-runtime.py"))
        result = lifecycle.batch_deliver(batch, root, base, tip)
    delivered = git_output(root, "rev-parse", "HEAD")
    assert result["remote"] == delivered
    assert git_output(root, "show", "-s", "--format=%P", delivered).split() == [base, tip]
    assert (root / "own.txt").is_file()
    assert not (root / "changes/batch-example").exists()
    assert member.exists()
    assert not batch.exists()
    assert root.exists()
    assert result["retained_worktrees"] == [
        {"branch": "plan/example", "worktree": str(member), "reason": "active_runtime"}
    ]
    cleaned = ops.cleanup(root, worktree=member)
    assert removed_outcomes(cleaned["removed"]) == {"plan/example": "delivered"}
    assert not member.exists()


def test_batch_open_prepares_admitted_source_when_delivery_has_no_prepare_gate(repository):
    root, state = repository
    manifest = root / "signetum.toml"
    current = manifest.read_text()
    old = current[: current.index("[[validation.gates]]")]
    old += '[[validation.gates]]\nname="member"\nshards=["test:check"]\n'
    old += '[[validation.gates]]\nname="final"\nshards=["test:check"]\n'
    manifest.write_text(old)
    policy = root / ".agents/signetum/repo.yaml"
    policy.write_text("delivery:\n  branch: main\n  state: .signetum/delivery\n")
    git_output(root, "commit", "-am", "retain an older delivery configuration")
    git_output(root, "push", "origin", "main")
    base = git_output(root, "rev-parse", "HEAD")
    member = root.parent / "protocol-member"
    git_output(root, "worktree", "add", "-b", "plan/protocol-upgrade", str(member), base)
    ops.write_record(
        ops.state_root(root), ops.WorkspaceRecord(1, "plan/protocol-upgrade", base, "member")
    )
    commit_approval(member)
    (member / "signetum.toml").write_text(current)
    (member / ".agents/signetum/repo.yaml").write_text("delivery:\n  branch: main\n")
    git_output(member, "commit", "-am", "migrate approved protocol configuration")
    commit_file(member, "implementation.txt")
    lifecycle.validate(member, "member")
    pending = ops.open_workspace(
        member,
        "batch/protocol-upgrade",
        base,
        kind="batch",
        members=("plan/protocol-upgrade",),
        authorization=ops.BatchAuthorization(
            "Owner",
            "Owner authorized the fixture batch",
            "2026-11-09T00:00:00+00:00",
            ("plan/protocol-upgrade",),
        ),
    )
    preparation = pending["preparation"]
    assert isinstance(preparation, dict) and preparation["status"] == "pending_admission"
    opened_batch = lifecycle.batch_open(
        member, (member,), actor="Owner", source="Owner authorized the fixture batch"
    )
    assert (
        read_record(
            state_root(Path(str(opened_batch["worktree"]))), "batch/protocol-upgrade"
        ).engine
        is None
    )
    preparation = opened_batch["preparation"]
    static = opened_batch["static"]
    assert isinstance(preparation, dict) and preparation["status"] == "prepared"
    assert isinstance(static, dict) and static["executed"] == ["test:check"]
    assert (state / "attempts").read_text() == "2"
    assert git_output(root, "rev-parse", "HEAD") == base


@pytest.mark.parametrize("obstruction", ["root-link", "target-link", "occupied"])
def test_open_refuses_unsafe_managed_destinations_before_creation(repository, obstruction):
    root, state = repository
    target = workspace_destination(root, "plan/unsafe")
    outside = root.parent / "outside-managed"
    outside.mkdir()
    if obstruction == "root-link":
        target.parent.symlink_to(outside, target_is_directory=True)
    else:
        target.parent.mkdir(exist_ok=True)
        if obstruction == "target-link":
            target.symlink_to(outside, target_is_directory=True)
        else:
            target.mkdir()
            (target / "user-file").write_text("retain")
    before = git_output(root, "worktree", "list", "--porcelain")
    with pytest.raises((AdmissionError, ops.WorkspaceError), match=r"escape|inside|exists"):
        ops.workspace_open(root, "plan/unsafe", "HEAD")
    assert git_output(root, "worktree", "list", "--porcelain") == before
    assert not (state / "attempts").exists()
    if obstruction == "occupied":
        assert (target / "user-file").read_text() == "retain"


@pytest.mark.parametrize("landing", ["cherry-pick", "squash"])
def test_cleanup_removes_a_workspace_whose_commits_reached_delivery(repository, landing):
    root, _ = repository
    member = opened(root, "plan/landed")
    first = commit_file(member, "first.txt", "one\n")
    second = commit_file(member, "second.txt", "two\n")
    pending = opened(root, "plan/pending")
    commit_file(pending, "pending.txt")
    if landing == "cherry-pick":
        land(root, first, second)
        # A later delivery edit defeats the tree comparison; patch identity remains.
        commit_file(root, "first.txt", "edited after landing\n")
    else:
        (root / "first.txt").write_text("one\n")
        git_output(root, "add", "first.txt")
        commit_file(root, "second.txt", "two\n")
    git_output(root, "push", "origin", "main")

    result = ops.cleanup(root, all_delivered=True)

    assert removed_outcomes(result["removed"]) == {"plan/landed": "contained"}
    removed = result["removed"]
    assert isinstance(removed, list)
    if landing == "cherry-pick":
        assert removed[0]["proof"] == "patch"
        assert removed[0]["commits"] == sorted((first, second))
    else:
        assert removed[0]["proof"] == "tree"
        assert removed[0]["paths"] == ["first.txt", "second.txt"]
    assert result["retained"] == [
        {"branch": "plan/pending", "worktree": str(pending), "reason": "not_contained"}
    ]
    assert pending.exists()
    retired = tuple((state_root(root) / "retired").rglob("*.json"))
    assert len(retired) == 1
    assert json.loads(retired[0].read_text())["record"]["branch"] == "plan/landed"


@pytest.mark.parametrize("own_content", [False, True])
def test_cleanup_removes_a_batch_whose_member_landed_through_another_batch(repository, own_content):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    member = opened(root, "plan/shared")
    commit_file(member, "shared.txt")
    batch = Path(str(ops.open_workspace(root, "batch/superseded", base, kind="batch")["worktree"]))
    git_output(batch, "merge", "--no-ff", "--no-commit", "plan/shared")
    if own_content:
        # A resolution of the merge's own is content outside every commit.
        (batch / "resolution.txt").write_text("only in this merge")
        git_output(batch, "add", "resolution.txt")
    git_output(batch, "commit", "-m", "admit plan/shared")
    publish_member(root, member)

    result = ops.cleanup(root, all_delivered=True)

    if own_content:
        assert removed_outcomes(result["removed"]) == {"plan/shared": "delivered"}
        assert result["retained"] == [
            {"branch": "batch/superseded", "worktree": str(batch), "reason": "not_contained"}
        ]
    else:
        assert removed_outcomes(result["removed"]) == {
            "plan/shared": "delivered",
            "batch/superseded": "contained",
        }


@pytest.mark.parametrize("change", ["untracked", "modified"])
def test_cleanup_never_removes_a_contained_workspace_with_uncommitted_work(repository, change):
    root, _ = repository
    member = opened(root, "plan/unfinished")
    land(root, commit_file(member, "own.txt"))
    if change == "untracked":
        (member / "notes.txt").write_text("keep")
    else:
        (member / "own.txt").write_text("keep")

    result = ops.cleanup(root, all_delivered=True)

    assert result["removed"] == []
    assert result["retained"] == [
        {"branch": "plan/unfinished", "worktree": str(member), "reason": "dirty"}
    ]
    assert member.exists()
    with pytest.raises(AdmissionError, match="--discard requires one selected"):
        ops.cleanup(root, all_delivered=True, discard=True)


def test_abandonment_requires_the_owners_confirmation_of_the_exact_tip(
    repository, monkeypatch, capsys
):
    root, _ = repository
    member = opened(root, "plan/abandoned")
    tip = commit_file(member, "own.txt")
    owner = {"actor": "Owner", "source": "Owner chat 2026-11-04", "reason": "Superseded idea."}

    def abandon(worktree, expected, **override):
        fields = {**owner, **override}
        return ops.workspace_abandon(
            root,
            worktree,
            expected,
            actor=fields["actor"],
            source=fields["source"],
            reason=fields["reason"],
        )

    for missing in owner:
        with pytest.raises(AdmissionError, match=f"--{missing}"):
            abandon(member, tip, **{missing: " "})
    with pytest.raises(AdmissionError, match="full commit"):
        abandon(member, tip[:12])
    with pytest.raises(AdmissionError, match="confirmed tip"):
        abandon(member, git_output(root, "rev-parse", "HEAD"))
    (member / "notes.txt").write_text("uncommitted")
    with pytest.raises(AdmissionError, match="dirty"):
        abandon(member, tip)
    (member / "notes.txt").unlink()
    contained = opened(root, "plan/contained")
    landed = commit_file(contained, "landed.txt")
    land(root, landed)
    with pytest.raises(AdmissionError, match="proves contained; use maintenance cleanup"):
        abandon(contained, landed)
    assert member.exists() and contained.exists()

    unrelated = root.parent / "unrelated"
    unrelated.mkdir()
    git_output(unrelated, "init", "-b", "main")
    monkeypatch.chdir(unrelated)
    capsys.readouterr()
    arguments = ["workspace-abandon", str(member), tip]
    for name, value in owner.items():
        arguments += [f"--{name}", value]

    assert maintenance.main(arguments) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["outcome"] == "abandoned"
    assert not member.exists()
    assert run_git(root, "rev-parse", "--verify", "refs/heads/plan/abandoned").returncode
    retirement = json.loads(Path(str(result["retirement"])).read_text())
    assert retirement["outcome"] == "abandoned"
    assert retirement["tip"] == tip
    assert retirement["reason"] == "Superseded idea."
    assert retirement["authorization"]["actor"] == "Owner"
    assert retirement["authorization"]["source"] == "Owner chat 2026-11-04"
    assert retirement["record"]["kind"] == "member"


def test_leftovers_lists_and_removes_only_confirmed_outside_work(repository, monkeypatch, capsys):
    root, _ = repository
    owner: Any = {"actor": "Owner", "source": "Owner chat 2026-11-08", "reason": "Dropped spike."}
    outside = root.parent / "outside-checkout"
    git_output(root, "worktree", "add", "-b", "spike/outside", str(outside))
    outside_tip = commit_file(outside, "spike.txt")
    loose = opened(root, "change/loose")
    loose_tip = commit_file(loose, "loose.txt")
    git_output(loose, "switch", "--detach")
    git_output(root, "branch", "merged/already")  # contained by main: not a leftover
    registered = opened(root, "plan/registered")
    commit_file(registered, "registered.txt")
    monkeypatch.chdir(root)
    capsys.readouterr()

    assert maintenance.main(["leftovers"]) == 0

    listed = json.loads(capsys.readouterr().out)["leftovers"]
    assert {(item["kind"], item["branch"]) for item in listed} == {
        ("unregistered_checkout", "spike/outside"),
        ("branch_without_checkout", "change/loose"),
    }
    assert all(item["tip"] in item["remove"] for item in listed)
    with pytest.raises(AdmissionError, match="confirmed tip"):
        ops.branch_abandon(root, "change/loose", outside_tip, **owner)
    with pytest.raises(AdmissionError, match="checked out"):
        ops.branch_abandon(root, "spike/outside", outside_tip, **owner)
    assert run_git(root, "rev-parse", "--verify", "refs/heads/change/loose").returncode == 0

    removed = ops.branch_abandon(root, "change/loose", loose_tip, **owner)
    abandoned = ops.workspace_abandon(root, outside, outside_tip, **owner)

    assert run_git(root, "rev-parse", "--verify", "refs/heads/change/loose").returncode
    retirement = json.loads(Path(str(removed["retirement"])).read_text())
    assert retirement["tip"] == loose_tip and retirement["outcome"] == "abandoned"
    assert retirement["authorization"]["source"] == "Owner chat 2026-11-08"
    assert not outside.exists() and abandoned["tip"] == outside_tip
    capsys.readouterr()
    assert maintenance.main(["leftovers"]) == 0
    assert json.loads(capsys.readouterr().out)["leftovers"] == []


def test_delivery_sweeps_every_workspace_that_proves_its_outcome(repository):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    sibling = opened(root, "plan/sibling")
    landed = commit_file(sibling, "sibling.txt")
    pending = opened(root, "plan/pending")
    commit_file(pending, "pending.txt")
    fresh = opened(root, "plan/fresh")
    member = opened(root, "plan/example")
    commit_approval(member, "example")
    git_output(member, "cherry-pick", landed)
    commit_file(member, "own.txt")
    lifecycle.validate(member, "member")
    batch = Path(
        str(
            lifecycle.batch_open(
                root, (member,), actor="Owner", source="Owner authorized the fixture batch"
            )["worktree"]
        )
    )
    final = lifecycle.validate(batch, "final")
    tip = final["source"]
    assert isinstance(tip, str)

    result = lifecycle.batch_deliver(batch, root, base, tip)

    assert removed_outcomes(result["removed_worktrees"]) == {
        "plan/example": "delivered",
        "batch/example": "delivered",
        "plan/sibling": "contained",
    }
    retained = result["retained_worktrees"]
    assert isinstance(retained, list)
    assert {row["branch"]: row["reason"] for row in retained} == {
        "plan/pending": "not_contained",
        "plan/fresh": "fresh_workspace",
    }
    assert pending.exists() and fresh.exists()


def test_status_lists_each_workspace_with_the_outcome_it_proves(repository):
    root, _ = repository
    landed = opened(root, "plan/landed")
    tip = commit_file(landed, "landed.txt")
    pending = opened(root, "plan/pending")
    commit_file(pending, "pending.txt")
    land(root, tip)
    git_output(root, "worktree", "add", "--detach", str(root.parent / "detached"), "HEAD")

    view = workflow_status(root, snapshot(root), source=git_output(root, "rev-parse", "HEAD"))

    assert view["workspaces"] == [
        {
            "branch": "plan/landed",
            "worktree": str(landed),
            "kind": "member",
            "outcome": "contained",
            "reason": None,
        },
        {
            "branch": "plan/pending",
            "worktree": str(pending),
            "kind": "member",
            "outcome": None,
            "reason": "not_contained",
        },
    ]
    assert landed.exists()


DECLARED_RUN_TOOL = wt.run_tool


def test_preparation_may_rebuild_ignored_state_and_names_the_adapter_on_failure(
    repository, monkeypatch, tmp_path
):
    root, _ = repository
    shim = tmp_path / "mise"
    shim.write_text('#!/bin/sh\nshift 2\nexec "$@"\n')  # drops "exec --"
    shim.chmod(0o755)
    monkeypatch.setattr(wt, "mise_executable", lambda: str(shim))
    monkeypatch.setattr(wt, "run_tool", DECLARED_RUN_TOOL)
    rebuild = (
        "from pathlib import Path; import json, sys; p = Path('prepared.state'); "
        "stale = Path('stale').exists(); "
        "print(json.dumps({'expected': 'run just prepare --rebuild-stale'})) if stale else "
        "p.write_text('rebuilt'); sys.exit(4 if stale else 0)"
    )
    preparation_command(root, [sys.executable, "-c", rebuild])
    (root / ".gitignore").write_text("prepared.state\nstale\n.worktrees/\n")
    git_output(root, "add", "signetum.toml", ".gitignore")
    git_output(root, "commit", "-m", "rebuild prepared state")
    member = opened(root, "plan/rebuild")
    assert (member / "prepared.state").read_text() == "rebuilt"

    (member / "stale").touch()
    with pytest.raises(OperationFailed) as refusal:
        ops.worktree_prepare(member)

    assert "test:prepare" in str(refusal.value) and sys.executable in str(refusal.value)
    assert "just prepare --rebuild-stale" in refusal.value.expected


def test_batch_open_authorizes_combination_fix_without_a_change_draft(repository, monkeypatch):
    root, _ = repository
    monkeypatch.setattr(ops, "install_commit_check", install_commit_check)
    base = git_output(root, "rev-parse", "HEAD")
    member = opened(root, "plan/example")
    commit_approval(member, "example")
    commit_file(member, "own.txt")
    lifecycle.validate(member, "member")
    opened_batch = lifecycle.batch_open(
        root, (member,), actor="Owner", source="Owner authorized integration"
    )
    batch = Path(str(opened_batch["worktree"]))
    record = read_record(state_root(batch), git_output(batch, "branch", "--show-current"))
    assert record.schema_version == 2
    assert record.authorization is not None
    assert record.authorization.actor == "Owner"
    assert record.authorization.members == ("plan/example",)
    assert not (batch / "changes/batch-example").exists()
    assert not git_output(batch, "status", "--porcelain")
    (batch / "combined.txt").write_text("fix under batch authorization")
    git_output(batch, "add", "combined.txt")
    git_output(batch, "commit", "-m", "fix the combination")
    fix = git_output(batch, "rev-parse", "HEAD")
    final = lifecycle.validate(batch, "final")
    review = final["delivery_review"]
    assert isinstance(review, dict)
    inputs = review["inputs"]
    item = next(item for item in inputs["batch_commits"] if item["commit"] == fix)
    assert item["authority"] == "batch-authorization"
    repair = inputs["combination_repairs"][0]
    assert repair["commit"] == fix
    assert repair["authorization"]["source"] == "Owner authorized integration"
    assert repair["subject"] == "fix the combination"
    assert "combined.txt" in repair["diffstat"]
    assert git_output(root, "rev-parse", "HEAD") == base


def test_a_tool_missing_from_the_default_mise_environment_runs_under_the_declared_one(
    repository, monkeypatch, tmp_path
):
    del repository
    tools = tmp_path / "maintainer-tools"
    tools.mkdir()
    tool = tools / "signetum-fixture-wt"
    tool.write_text("#!/bin/sh\nprintf maintained\n")
    tool.chmod(0o755)
    shim = tmp_path / "mise"
    shim.write_text(
        '#!/bin/sh\nshift 2\n[ "${MISE_ENV:-}" = maintainer ] && PATH="'
        + str(tools)
        + ':$PATH"\nexec "$@"\n'
    )
    shim.chmod(0o755)
    monkeypatch.setattr(wt, "mise_executable", lambda: str(shim))
    monkeypatch.setattr(wt, "run_tool", DECLARED_RUN_TOOL)
    monkeypatch.delenv("MISE_ENV", raising=False)
    declared = tmp_path / "declared"
    declared.mkdir()
    (declared / "mise.maintainer.toml").write_text('[tools]\nworktrunk = "0.74.0"\n')
    other = tmp_path / "other"
    other.mkdir()
    (other / "mise.staging.toml").write_text("[tools]\n")

    assert wt.run_tool(declared, (tool.name,)).stdout == "maintained"
    assert wt.run_tool(declared, (tool.name,)).stdout == "maintained"
    with pytest.raises(InfrastructureError) as refusal:
        wt.run_tool(other, (tool.name,))
    assert tool.name in str(refusal.value) and "staging" in str(refusal.value)


def test_preparation_reinstalls_check_after_hooks_path_changes(repository, monkeypatch):
    root, _ = repository
    monkeypatch.setattr(ops, "install_commit_check", install_commit_check)
    git_output(root, "config", "extensions.worktreeConfig", "true")
    member = opened(root, "plan/hook-preparation")
    commit_approval(member)
    hooks = state_root(member) / "project-hooks"
    preparation_command(member, ["git", "config", "--worktree", "core.hooksPath", str(hooks)])
    git_output(member, "add", "signetum.toml")
    git_output(member, "commit", "-m", "prepare a project hooks directory")

    ops.worktree_prepare(member)

    assert install_commit_check(member)["status"] == "active"
    assert (hooks / "reference-transaction").is_file()
    assert not git_output(member, "for-each-ref", "refs/signetum/probe/")
    assert git_output(member, "status", "--porcelain") == ""


def test_foreign_hook_chain_is_probed_and_enforces_approval(repository, monkeypatch):
    root, _ = repository
    # Opening remains allowed even while the project hook is not chained.
    hooks = state_root(root) / "foreign-hooks"
    hooks.mkdir()
    hook = hooks / "reference-transaction"
    hook.write_text("#!/bin/sh\nexit 0\n")
    hook.chmod(0o755)
    git_output(root, "config", "core.hooksPath", str(hooks))
    monkeypatch.setattr(ops, "install_commit_check", install_commit_check)
    member = opened(root, "plan/chained")
    before = hook.read_bytes()
    inactive = install_commit_check(member)
    assert inactive["status"] == "inactive"
    assert hook.read_bytes() == before
    status = workflow_status(
        member, snapshot(member), source=git_output(member, "rev-parse", "HEAD")
    )
    check = status["commit_check"]
    assert isinstance(check, dict)
    assert check["status"] == "inactive"

    hook.write_text("#!/bin/sh\n" + CHAIN + "\n")
    assert commit_check_status(member)["status"] == "active"
    (member / "implementation.txt").write_text("unapproved\n")
    git_output(member, "add", "implementation.txt")
    refused = run_git(member, "commit", "-m", "implementation before approval")
    assert refused.returncode != 0
    assert "approval" in refused.stderr
    assert not git_output(member, "for-each-ref", "refs/signetum/probe/")


def test_pinned_batch_refuses_changed_engine_before_any_batch_work(repository, monkeypatch):

    root, state = repository
    base = git_output(root, "rev-parse", "HEAD")
    observed = runtime_identity.identity()
    batch = Path(
        str(
            ops.open_workspace(
                root,
                "batch/pinned",
                base,
                kind="batch",
                engine=BatchEngine(
                    str(observed["version"]), str(observed["implementation"]), "skill"
                ),
            )["worktree"]
        )
    )
    pin = read_record(state_root(batch), "batch/pinned").engine
    assert pin is not None
    original = runtime_identity.identity
    monkeypatch.setattr(
        runtime_identity, "identity", lambda: {**original(), "implementation": "sha256:" + "f" * 64}
    )
    before = git_output(batch, "rev-parse", "HEAD")
    attempts = (state / "attempts").read_text() if (state / "attempts").exists() else None
    for action in (
        lambda: lifecycle.admit(batch, ()),
        lambda: lifecycle.continue_batch(batch),
        lambda: lifecycle.sync_batch(batch),
        lambda: lifecycle.validate(batch, "final"),
        lambda: lifecycle.batch_deliver(batch, root, base, before),
    ):
        with pytest.raises(AdmissionError) as refused:
            action()
        assert pin.version in str(refused.value)
        assert pin.implementation in str(refused.value)
        assert "new batch" in refused.value.expected
    assert git_output(batch, "rev-parse", "HEAD") == before
    assert ((state / "attempts").read_text() if (state / "attempts").exists() else None) == attempts
    status = workflow_status(batch, snapshot(batch), source=before)
    engine = status["engine"]
    assert isinstance(engine, dict)
    assert engine["status"] == "mismatch"


def test_foreign_checkout_cannot_open_batch(repository, monkeypatch):

    root, _ = repository
    monkeypatch.setattr(runtime_identity, "engine_source", lambda repository: "checkout")
    before = git_output(root, "worktree", "list", "--porcelain")
    with pytest.raises(AdmissionError) as refused:
        lifecycle.batch_open(root, (root,), name="foreign", actor="Owner", source="Approved")
    assert "installed Skill" in refused.value.expected
    assert git_output(root, "worktree", "list", "--porcelain") == before


def test_repository_pin_follows_batch_location_and_legacy_stays_unpinned(repository, monkeypatch):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    legacy = Path(str(ops.open_workspace(root, "batch/legacy", base, kind="batch")["worktree"]))
    status = workflow_status(legacy, snapshot(legacy), source=base)
    engine = status["engine"]
    assert isinstance(engine, dict) and engine["status"] == "unpinned"

    batch = Path(
        str(
            ops.open_workspace(
                root,
                "batch/repository-engine",
                base,
                kind="batch",
                engine=BatchEngine("0.7.0", "sha256:" + "0" * 64, "repository"),
            )["worktree"]
        )
    )
    monkeypatch.setattr(runtime_identity, "engine_source", actual_engine_source)
    monkeypatch.setattr(runtime_identity, "__file__", str(batch / "engine.py"))
    status = workflow_status(batch, snapshot(batch), source=base)
    engine = status["engine"]
    assert isinstance(engine, dict) and engine["status"] == "matched"
    # The repository pin accepts source evolution at the same batch location.
    (batch / "engine.py").write_text("# admitted engine change\n")
    status = workflow_status(batch, snapshot(batch), source=base)
    engine = status["engine"]
    assert isinstance(engine, dict) and engine["status"] == "matched"
    monkeypatch.setattr(runtime_identity, "__file__", str(root / "engine.py"))
    status = workflow_status(batch, snapshot(batch), source=base)
    engine = status["engine"]
    assert isinstance(engine, dict) and engine["status"] == "mismatch"


def test_self_hosted_batch_open_enters_its_prepared_engine(repository, monkeypatch, tmp_path):
    root, _ = repository
    monkeypatch.setenv("MISE_TRUSTED_CONFIG_PATHS", str(tmp_path))
    source = Path(__file__).resolve().parents[1]
    engine = root / "skills/signetum/scripts/engine"
    shutil.copytree(
        source / "skills/signetum/scripts/engine",
        engine,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "dist", "*.egg-info"),
    )
    for name in ("pyproject.toml", "uv.lock", "mise.toml"):
        shutil.copy2(source / name, root / name)
    (root / ".gitignore").write_text(".venv/\n__pycache__/\n")
    preparation_command(root, ["uv", "sync", "--locked", "--python", sys.executable])
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "adopt repository engine for self-hosting")
    git_output(root, "push", "origin", "main")
    member = opened(root, "plan/self-hosted")
    commit_approval(member)
    commit_file(member, "self-hosted.txt")
    assert lifecycle.validate(member, "member")["status"] == "ready"
    monkeypatch.setattr(runtime_identity, "engine_source", actual_engine_source)
    monkeypatch.setattr(runtime_identity, "__file__", str(engine / "signetum/runtime_identity.py"))

    # The handoff must use the production environment isolation and result contract.
    monkeypatch.setattr(wt, "run_tool", actual_run_tool)

    result = lifecycle.batch_open(root, (member,), actor="Owner", source="Approved self-hosting")

    batch = Path(str(result["batch"]))
    pin = read_record(state_root(batch), branch_name(batch)).engine
    assert pin is not None and pin.source == "repository"
    assert (batch / "self-hosted.txt").is_file()
    assert result["admitted"]
    # The opening checkout cannot act for the batch after the handoff.
    with pytest.raises(AdmissionError):
        lifecycle.admit(batch, ())
