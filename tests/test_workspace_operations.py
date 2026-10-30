"""Real Git scenarios for supported workspace recovery and removal."""

import importlib
import json
import sys
from pathlib import Path

import pytest
from change_fixtures import approve_change, commit_approval

from signetum import lifecycle
from signetum import workspace_operations as ops
from signetum import worktrunk as wt
from signetum.git import git_output, run_git
from signetum.operations import AdmissionError, InfrastructureError, MergeConflict, OperationFailed
from signetum.workspaces import branch_name, read_record, state_root


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
    member = root.parent / "unregistered"
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


def test_sync_refuses_a_batch_as_the_receiving_workspace(repository):
    root, _ = repository
    batch = Path(str(ops.open_workspace(root, "batch/receiver", "HEAD", kind="batch")["worktree"]))
    before = git_output(batch, "rev-parse", "HEAD")
    with pytest.raises(AdmissionError, match="implementation member"):
        ops.workspace_sync(batch)
    assert git_output(batch, "rev-parse", "HEAD") == before


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


def test_batch_discard_cannot_remove_an_implementation_member(repository):
    root, _ = repository
    member = opened(root, "plan/retain-member")
    with pytest.raises(AdmissionError, match="batch"):
        ops.batch_discard(member)
    assert member.exists()
    assert branch_name(member) == "plan/retain-member"


def commit_file(repository, name, value="work"):
    (repository / name).write_text(value)
    git_output(repository, "add", name)
    git_output(repository, "commit", "-m", f"implement {name}")
    return git_output(repository, "rev-parse", "HEAD")


def publish_member(repository, member):
    git_output(repository, "merge", "--no-ff", branch_name(member), "-m", "deliver fixture")
    git_output(repository, "push", "origin", "main")


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
    result = lifecycle.changed(member, True)
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
        lifecycle.changed(member, True)


def test_changed_refuses_workspace_without_committed_contribution(repository):
    root, _ = repository
    member = opened(root, "plan/no-contribution")
    with pytest.raises(AdmissionError, match="no committed contribution"):
        lifecycle.changed(member, True)


def test_changed_without_provider_plans_full_checks_for_unexplained_paths(repository):
    root, _ = repository
    manifest = root / "signetum.toml"
    commit_file(
        root, "signetum.toml", manifest.read_text().replace('paths = ["**"]', 'paths = ["src/**"]')
    )
    member = opened(root, "plan/no-selection")
    commit_file(member, "unexplained.md")
    result = lifecycle.changed(member, True)
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
    result = lifecycle.changed(member, True)
    assert result["status"] == "selection-only"
    assert result["executed"] == []
    assert result["shards"] == ("test:check",)
    monkeypatch.chdir(member)
    assert lifecycle.main(["changed", "--explain"]) == 0
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
    assert "worktree-prepare and ready" in refusal.value.expected
    assert run_git(member, "rev-parse", "--verify", "MERGE_HEAD").returncode == 0


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
    assert result["removed"] == [str(delivered)]
    retained = result["retained"]
    assert isinstance(retained, list)
    reasons = {row["branch"]: row["reason"] for row in retained}
    assert reasons == {
        "main": "protected",
        "plan/dirty": "dirty",
        "plan/advanced": "undelivered",
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
        assert result["removed"] == [str(member)]
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


def test_clean_unpublished_batch_can_be_discarded(repository):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    batch = Path(str(ops.open_workspace(root, "batch/test", base, kind="batch")["worktree"]))
    result = ops.batch_discard(batch)
    assert result["status"] == "discarded"
    assert not batch.exists()
    assert run_git(root, "show-ref", "--verify", "refs/heads/batch/test").returncode != 0


def test_published_batch_is_not_discarded(repository):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    batch = Path(str(ops.open_workspace(root, "batch/test", base, kind="batch")["worktree"]))
    git_output(batch, "push", "origin", "batch/test")
    with pytest.raises(AdmissionError, match="published batch"):
        ops.batch_discard(batch)
    assert batch.exists()


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
    changed = lifecycle.changed(member, True)["files"]
    assert isinstance(changed, tuple)
    assert set(changed) == {
        "own.txt",
        "changes/dependent/review.toml",
        "changes/dependent/specs/behavior.toml",
        "changes/dependent/plans/behavior.md",
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


def test_validated_delivery_uses_shared_cleanup_and_keeps_the_delivery_worktree(repository):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    member = opened(root, "plan/example")
    commit_approval(member, "example")
    commit_file(member, "own.txt")
    lifecycle.validate(member, "member")
    opened_batch = lifecycle.batch_open(root, (member,))
    batch = Path(str(opened_batch["worktree"]))
    final = lifecycle.validate(batch, "final")
    tip = final["source"]
    assert isinstance(tip, str)
    result = lifecycle.batch_deliver(batch, root, base, tip)
    delivered = git_output(root, "rev-parse", "HEAD")
    assert result["remote"] == delivered
    assert git_output(root, "show", "-s", "--format=%P", delivered).split() == [base, tip]
    assert (root / "own.txt").is_file()
    assert not member.exists()
    assert not batch.exists()
    assert root.exists()
    assert result["retained_worktrees"] == []


@pytest.fixture(params=["engine", "template"], autouse=True)
def lifecycle_frontend(request, monkeypatch):
    """Run every disposable Git workspace contract against both maintained outputs."""
    if request.param == "engine":
        return
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[1] / "template/.agents/repo-dev/runtime")
    )
    for name, module in {
        "lifecycle": "lifecycle",
        "ops": "workspace_operations",
        "wt": "worktrunk",
    }.items():
        monkeypatch.setitem(globals(), name, importlib.import_module("_signetum_runtime." + module))
    errors = importlib.import_module("_signetum_runtime.operations")
    for name in ("AdmissionError", "InfrastructureError", "MergeConflict", "OperationFailed"):
        monkeypatch.setitem(globals(), name, getattr(errors, name))
    monkeypatch.setitem(
        globals(),
        "ValidationExecutionError",
        importlib.import_module("_signetum_runtime.execution").ValidationExecutionError,
    )


def test_batch_open_prepares_admitted_source_when_delivery_has_no_prepare_gate(repository):
    root, state = repository
    manifest = root / "signetum.toml"
    current = manifest.read_text()
    old = current[: current.index("[[validation.gates]]")]
    old += '[[validation.gates]]\nname="member"\nshards=["test:check"]\n'
    old += '[[validation.gates]]\nname="final"\nshards=["test:check"]\n'
    manifest.write_text(old)
    policy = root / ".agents/repo-dev/repo.yaml"
    policy.write_text("delivery:\n  branch: main\n  state: .signetum/delivery\n")
    git_output(root, "commit", "-am", "retain an older delivery configuration")
    git_output(root, "push", "origin", "main")
    base = git_output(root, "rev-parse", "HEAD")
    member = root.parent / "protocol-member"
    git_output(root, "worktree", "add", "-b", "plan/protocol-upgrade", str(member), base)
    ops.write_record(
        ops.state_root(root), ops.WorkspaceRecord(1, "plan/protocol-upgrade", base, "member")
    )
    (member / "signetum.toml").write_text(current)
    (member / ".agents/repo-dev/repo.yaml").write_text("delivery:\n  branch: main\n")
    commit_approval(member)
    commit_file(member, "implementation.txt")
    lifecycle.validate(member, "member")
    pending = ops.open_workspace(
        member, f"batch/{base}", base, kind="batch", members=(str(member),)
    )
    preparation = pending["preparation"]
    assert isinstance(preparation, dict) and preparation["status"] == "pending_admission"
    opened_batch = lifecycle.batch_open(member, (member,))
    preparation = opened_batch["preparation"]
    static = opened_batch["static"]
    assert isinstance(preparation, dict) and preparation["status"] == "prepared"
    assert isinstance(static, dict) and static["executed"] == ["test:check"]
    assert (state / "attempts").read_text() == "1"
    assert git_output(root, "rev-parse", "HEAD") == base
