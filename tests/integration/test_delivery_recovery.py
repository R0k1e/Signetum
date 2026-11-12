"""Delivery survives remote rejection and interruption without losing local state."""

import json
import subprocess
from pathlib import Path
from shutil import which

import pytest
from change_fixtures import approve_change
from operation_messages import operation_message
from signetum import lifecycle
from signetum import workspace_operations as workspace_ops
from signetum import worktrunk as wt
from signetum.execution_review import execution_review_inputs
from signetum.manifest import load_manifest
from signetum.operation_records import commit_message, load_index
from signetum.operations import InfrastructureError, OperationFailed
from signetum.publication_binding import bind_publication, review_local_inputs
from signetum.workspaces import WorkspaceRecord, write_record
from test_batch_admission import MANIFEST


def git(repository: Path, *arguments: str) -> str:
    executable = which("git")
    if executable is None:
        raise RuntimeError("Git is required for delivery scenarios")
    return subprocess.run(  # nosec B603
        (executable, "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init", "-b", "main")
    git(target, "config", "user.name", "Delivery Test")
    git(target, "config", "user.email", "delivery@example.invalid")
    (target / "content").write_text("base")
    (target / "signetum.toml").write_text(MANIFEST)
    policy = target / ".agents/signetum/repo.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("delivery:\n  branch: main\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "base")
    base = git(target, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    git(target, "remote", "add", "origin", str(remote))
    git(target, "push", "origin", "main")
    source = tmp_path / "batch"
    git(target, "worktree", "add", "-b", "batch/test", str(source))
    approve_change(source, "delivered")
    git(source, "add", ".")
    git(source, "commit", "-m", "approve the batch-owned change")
    (source / "content").write_text("delivered")
    git(source, "commit", "-am", "implement")
    tip = git(source, "rev-parse", "HEAD")
    write_record(
        lifecycle._state_root(source),
        WorkspaceRecord(schema_version=1, branch="batch/test", base=base, kind="batch"),
    )
    receipts = lifecycle._receipt_root(source)
    review = {
        "inputs": execution_review_inputs(
            source, load_manifest(source / "signetum.toml"), base, tip, receipts
        )
    }
    evidence = {"valid": True}
    (receipts / "final-test.json").write_text(
        json.dumps(
            {
                "source": tip,
                "base": base,
                "valid": True,
                "delivery_review": review,
                "evidence": evidence,
                "publication_binding": bind_publication(
                    source,
                    source=tip,
                    base=base,
                    review=review,
                    evidence=evidence,
                    local_inputs=review_local_inputs(source, review["inputs"], receipts),
                    members=[],
                    plans=[],
                ).document(),
            }
        )
    )
    (receipts / "final-zzz.json").write_text(
        json.dumps({"source": base, "base": base, "valid": True})
    )
    monkeypatch.setattr(lifecycle, "_attested_base", lambda *args: base)
    monkeypatch.setattr(lifecycle, "_delivery_provenance", lambda *args: ([], []))
    return source, target, remote, base, tip


def test_rejected_push_keeps_target_at_base(tmp_path, monkeypatch):
    source, target, remote, base, tip = delivery(tmp_path, monkeypatch)
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    message = "Merge test into main\n"

    with pytest.raises(OperationFailed):
        lifecycle.batch_deliver(source, target, base, tip, message=message)

    assert git(target, "rev-parse", "HEAD") == base
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == base
    hook.unlink()
    result = lifecycle.batch_deliver(source, target, base, tip, message=message)
    landed = git(target, "rev-parse", "HEAD")
    assert result["remote"] == landed
    assert commit_message(target, landed) == message
    assert "Signetum-" not in commit_message(target, landed)
    proof = load_index(target).for_commit(landed)
    assert proof is not None
    assert proof["proof"] == {
        "commit": landed,
        "parents": [base, tip],
        "tree": git(target, "rev-parse", f"{tip}^{{tree}}"),
    }
    assert git(target, "show", "-s", "--format=%P", landed).split() == [base, tip]


def test_published_delivery_resumes_local_move(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    original = lifecycle._git

    def interrupt(repository, *arguments, **kwargs):
        if repository == target and arguments[:2] == ("merge", "--ff-only"):
            raise lifecycle.AdmissionError("simulated interruption after publication")
        return original(repository, *arguments, **kwargs)

    monkeypatch.setattr(lifecycle, "_git", interrupt)
    with pytest.raises(lifecycle.AdmissionError, match="simulated interruption"):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    published = git(target, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert published != base
    assert git(target, "rev-parse", "HEAD") == base

    monkeypatch.setattr(lifecycle, "_git", original)
    result = lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert result["remote"] == published
    assert git(target, "rev-parse", "HEAD") == published


def test_delivery_defers_cleanup_and_retry_recognizes_publication(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    first = lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    cleanup = first["cleanup"]
    assert isinstance(cleanup, dict) and cleanup["status"] == "pending"
    assert source.is_dir()
    published = git(target, "rev-parse", "HEAD")
    result = lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert result["remote"] == published
    assert source.is_dir()


def test_unrelated_remote_change_is_refused_without_local_move(tmp_path, monkeypatch):
    source, target, remote, base, tip = delivery(tmp_path, monkeypatch)
    git(source, "push", "origin", f"{tip}:refs/heads/other")
    git(remote, "update-ref", "refs/heads/main", tip)
    with pytest.raises(lifecycle.AdmissionError, match="remote delivery branch"):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert git(target, "rev-parse", "HEAD") == base


def test_delivery_refuses_a_target_outside_the_validated_policy(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    git(target, "switch", "-c", "unintended")
    git(target, "push", "origin", "unintended")
    with pytest.raises(lifecycle.AdmissionError, match="repository-declared delivery branch"):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert git(target, "rev-parse", "HEAD") == base
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == base
    assert git(target, "ls-remote", "origin", "refs/heads/unintended").split()[0] == base


def test_unconfirmed_publication_keeps_local_target_and_can_resume(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    observe = lifecycle._remote_branch_tip
    calls = 0

    def unavailable_confirmation(repository, branch):
        nonlocal calls
        calls += 1
        return base if calls == 2 else observe(repository, branch)

    monkeypatch.setattr(lifecycle, "_remote_branch_tip", unavailable_confirmation)
    with pytest.raises(lifecycle.AdmissionError, match="remote delivery confirmation"):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    published = git(target, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert published != base
    assert git(target, "rev-parse", "HEAD") == base
    monkeypatch.setattr(lifecycle, "_remote_branch_tip", observe)
    delivered = lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert delivered["remote"] == published
    assert git(target, "rev-parse", "HEAD") == published


def test_matching_parents_with_different_tree_cannot_resume_delivery(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    other = git(
        source,
        "commit-tree",
        f"{base}^{{tree}}",
        "-p",
        base,
        "-p",
        tip,
        "-m",
        "unrelated tree with matching parents",
    )
    git(source, "push", "origin", f"{other}:refs/heads/main")
    with pytest.raises(lifecycle.AdmissionError, match="remote delivery branch"):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert git(target, "rev-parse", "HEAD") == base
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == other


@pytest.mark.parametrize("damage", ["missing", "altered"])
def test_delivery_refuses_missing_or_altered_source_journal_bindings_before_publication(
    tmp_path, monkeypatch, damage
):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    receipt = lifecycle._receipt_root(source) / "final-test.json"
    document = json.loads(receipt.read_text())
    bindings = document["delivery_review"]["inputs"]
    if damage == "missing":
        del bindings["source_journals"]
    else:
        bindings["source_journals"]["history_digest"] = "sha256:" + "0" * 64
    receipt.write_text(json.dumps(document))
    with pytest.raises(lifecycle.AdmissionError, match="publication binding changed"):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert git(target, "rev-parse", "HEAD") == base
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == base


@pytest.mark.parametrize(
    "damage", ["absent", "version", "evidence", "authority", "remote", "dirty"]
)
def test_publication_requires_current_final_binding(tmp_path, monkeypatch, damage):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    receipt = lifecycle._receipt_root(source) / "final-test.json"
    document = json.loads(receipt.read_text())
    if damage == "absent":
        del document["publication_binding"]
    elif damage == "version":
        document["publication_binding"]["schema_version"] = 99
    elif damage == "evidence":
        document["evidence"]["valid"] = False
    elif damage == "authority":
        record = lifecycle._state_root(source) / "workspaces/batch%2Ftest.json"
        record.write_bytes(record.read_bytes() + b"\n")
    elif damage == "remote":
        replacement = tmp_path / "replacement.git"
        replacement.mkdir()
        git(replacement, "init", "--bare")
        git(target, "push", str(replacement), f"{base}:refs/heads/main")
        git(source, "remote", "set-url", "origin", str(replacement))
    else:
        (source / "content").write_text("unreviewed")
    receipt.write_text(json.dumps(document))
    with pytest.raises(lifecycle.AdmissionError):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert git(target, "rev-parse", "HEAD") == base
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == base


def test_negotiated_remote_advance_to_candidate_ancestor_is_refused(tmp_path, monkeypatch):
    source, target, remote, base, tip = delivery(tmp_path, monkeypatch)
    git(source, "push", "origin", f"{tip}:refs/heads/seed")
    original = lifecycle._git
    raced = False

    def advance(repository, *arguments, **kwargs):
        nonlocal raced
        if "push" in arguments and not raced:
            raced = True
            git(remote, "update-ref", "refs/heads/main", tip)
        return original(repository, *arguments, **kwargs)

    monkeypatch.setattr(lifecycle, "_git", advance)
    # tip is the proposed delivery's second parent. Ordinary non-forced push
    # would accept that advance; the negotiated-old guard must refuse it.
    with pytest.raises(OperationFailed):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert raced
    assert git(target, "rev-parse", "HEAD") == base
    assert git(remote, "rev-parse", "refs/heads/main") == tip


@pytest.mark.parametrize("hook_exit", [0, 1])
def test_publication_preserves_configured_hook_and_its_input(tmp_path, monkeypatch, hook_exit):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    hooks = tmp_path / "configured hooks"
    hooks.mkdir()
    observed = tmp_path / "hook-input"
    hook = hooks / "pre-push"
    hook.write_text(f'#!/bin/sh\ncat > "{observed}"\nexit {hook_exit}\n')
    hook.chmod(0o755)
    references = tmp_path / "reference-input"
    reference_hook = hooks / "reference-transaction"
    reference_hook.write_text(f'#!/bin/sh\ncat >> "{references}"\n')
    reference_hook.chmod(0o755)
    git(source, "config", "core.hooksPath", str(hooks))
    original_hook = hook.read_bytes()
    if hook_exit:
        with pytest.raises(OperationFailed):
            lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
        assert git(target, "rev-parse", "HEAD") == base
    else:
        result = lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
        assert result["remote"] == git(target, "rev-parse", "HEAD")
        assert "refs/remotes/origin/main" in references.read_text()
    row = observed.read_text().split()
    assert row[2:] == ["refs/heads/main", base]
    assert hook.read_bytes() == original_hook
    assert git(source, "config", "core.hooksPath") == str(hooks)


def test_cleanup_failure_does_not_change_a_successful_publication(tmp_path, monkeypatch):
    source, target, _, base, tip = delivery(tmp_path, monkeypatch)
    result = lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    published = result["remote"]

    def unavailable(*args, **kwargs):
        raise InfrastructureError("fixture Worktrunk unavailable during cleanup")

    monkeypatch.setattr(wt, "worktrunk", unavailable)
    with pytest.raises(InfrastructureError):
        workspace_ops.cleanup(target, all_delivered=True)
    assert result["status"] == "delivered"
    assert git(target, "rev-parse", "HEAD") == published
    assert git(target, "ls-remote", "origin", "refs/heads/main").split()[0] == published
    assert source.exists()


def test_receive_pack_rejects_advance_after_pre_push_negotiation(tmp_path, monkeypatch):
    source, target, remote, base, tip = delivery(tmp_path, monkeypatch)
    git(source, "push", "origin", f"{tip}:refs/heads/seed")
    hooks = tmp_path / "configured-hooks"
    hooks.mkdir()
    hook = hooks / "pre-push"
    hook.write_text(
        f'#!/bin/sh\ncat > /dev/null\ngit --git-dir="{remote}" update-ref refs/heads/main {tip}\n'
    )
    hook.chmod(0o755)
    git(source, "config", "core.hooksPath", str(hooks))
    with pytest.raises(OperationFailed):
        lifecycle.batch_deliver(source, target, base, tip, message=operation_message())
    assert git(target, "rev-parse", "HEAD") == base
    assert git(remote, "rev-parse", "refs/heads/main") == tip
