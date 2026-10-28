"""Real Git scenarios for supported workspace recovery and removal."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from change_fixtures import approve_change

from signetum import lifecycle
from signetum import workspace_operations as ops
from signetum import worktrunk as wt
from signetum.git import git_output, run_git
from signetum.operations import AdmissionError, InfrastructureError, MergeConflict
from signetum.validation.execution import ValidationExecutionError
from signetum.workspaces import branch_name, read_record, state_root


@pytest.fixture
def repository(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    root.mkdir()
    git_output(root, "init", "-b", "main")
    git_output(root, "config", "user.name", "Workspace Test")
    git_output(root, "config", "user.email", "workspace@example.invalid")
    state = tmp_path / "preparation"
    state.mkdir()
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; p=Path(sys.argv[1]); "
        "n=p/'attempts'; n.write_text(str(int(n.read_text())+1) if n.exists() else '1'); "
        "sys.exit(13 if (p/'fail').exists() else 0)",
        str(state),
    ]
    (root / "signetum.toml").write_text(
        'schema_version = 2\n[signetum]\nprotocol = 2\ntemplate_version = "0.2.0"\n'
        '[repository]\narchitecture = "docs/ARCHITECTURE.md"\n'
        'specifications = "changes/*/specs/*.toml"\nplans = "changes/*/plans/*.md"\n'
        'decisions = "docs/decisions"\n'
        '[[impact.rules]]\nname = "all"\npaths = ["**"]\nshards = ["test:check"]\n'
        '[validation]\nmember_required = ["test:check"]\n'
        '[[validation.shards]]\nname = "test:check"\ncommand = ["true"]\n'
        '[[validation.shards]]\nname = "test:prepare"\ncommand = ' + json.dumps(command) + "\n"
        '[[validation.gates]]\nname = "prepare"\nshards = ["test:prepare"]\n'
        '[[validation.gates]]\nname = "member"\nshards = ["test:check"]\n'
        '[[validation.gates]]\nname = "final"\nshards = ["test:check"]\n'
        '[[validation.gates]]\nname = "batch"\nshards = ["test:check"]\n'
    )
    policy = root / ".agents/repo-dev/repo.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("delivery:\n  branch: main\n")
    (root / "seed.txt").write_text("base\n")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "base")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git_output(remote, "init", "--bare")
    git_output(root, "remote", "add", "origin", str(remote))
    git_output(root, "push", "origin", "main")

    def native_worktrunk(repository, arguments, *, json_output=False):
        del json_output
        if arguments[0] == "list":
            items = []
            for block in git_output(root, "worktree", "list", "--porcelain").split("\n\n"):
                fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
                branch = fields.get("branch", "").removeprefix("refs/heads/")
                if not branch:
                    continue
                path = Path(fields["worktree"])
                items.append(
                    {
                        "branch": branch,
                        "head": {"sha": fields["HEAD"]},
                        "worktree": {
                            "path": str(path),
                            "changes": {
                                "modified": bool(git_output(path, "status", "--porcelain")),
                            },
                        },
                    }
                )
            return {"schema": 2, "items": items}
        if arguments[0] == "switch":
            branch = arguments[arguments.index("--create") + 1]
            base = arguments[arguments.index("--base") + 1]
            path = tmp_path / ("wt-" + branch.replace("/", "-"))
            assert "--no-hooks" in arguments and "--no-cd" in arguments
            git_output(root, "worktree", "add", "-b", branch, str(path), base)
            return {}
        assert arguments[0] == "remove"
        assert {"--foreground", "--no-hooks", "--force-delete"} <= set(arguments)
        path = Path(arguments[-2])
        branch = branch_name(path)
        git_output(
            root, "worktree", "remove", *(("--force",) if "--force" in arguments else ()), str(path)
        )
        git_output(root, "branch", "-D", branch)
        return {"kind": "worktree", "branch_outcome": "deleted"}

    def native_preparation(repository, command, **kwargs):
        result = subprocess.run(
            command,
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=kwargs["timeout_seconds"],
        )
        if result.returncode:
            raise InfrastructureError(f"fixture preparation exited {result.returncode}")
        return result

    monkeypatch.setattr(wt, "worktrunk", native_worktrunk)
    monkeypatch.setattr(wt, "run_tool", native_preparation)
    return root, state


def opened(repository, branch):
    result = ops.workspace_open(repository, branch, git_output(repository, "rev-parse", "HEAD"))
    path = result["worktree"]
    assert isinstance(path, str)
    return Path(path)


def commit_file(repository, name, value="work"):
    (repository / name).write_text(value)
    git_output(repository, "add", name)
    git_output(repository, "commit", "-m", f"implement {name}")
    return git_output(repository, "rev-parse", "HEAD")


def publish_member(repository, member):
    git_output(repository, "merge", "--no-ff", branch_name(member), "-m", "deliver fixture")
    git_output(repository, "push", "origin", "main")


@pytest.mark.parametrize("fails", [False, True])
def test_changed_executes_selected_checks_without_granting_readiness(repository, fails):
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
    if fails:
        with pytest.raises(ValidationExecutionError, match="exited 1"):
            lifecycle.changed(member, True)
    else:
        result = lifecycle.changed(member, True)
        assert result["executed"] == ["test:check"]
    assert marker.exists()
    assert git_output(member, "rev-parse", "HEAD") == tip
    assert not (state_root(member) / "validation").exists()


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
