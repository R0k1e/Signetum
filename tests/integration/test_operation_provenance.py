"""Real Git proof for structured operation records.

Retained legacy and authorization coverage stays in the existing modules.
This module replaces superseded trailer assertions with exact message and
object checks, and keeps history before the first operation readable.
"""

import fcntl
import json
import subprocess
import sys

import pytest
from operation_messages import operation_message, operation_messages, write_operation_message
from signetum import lifecycle, maintenance
from signetum import operation_records as records
from signetum import workspace_operations as ops
from signetum.delivery import publish_batch
from signetum.execution_review import execution_review_inputs
from signetum.git import git_output, repository_path
from signetum.manifest import load_manifest
from signetum.operations import AdmissionError
from signetum.provenance import attested_base
from signetum.stacking import is_ancestor
from signetum.synchronization import authorize_source, verified_syncs
from signetum.workspaces import branch_name, read_record, state_root
from test_batch_synchronization import deliver, open_batch, parallel_batches, ready_member
from test_workspace_operations import commit_file, opened

_CHILD = """
import json, sys
from pathlib import Path
from signetum.operation_records import OperationIntent, begin_operation

payload = json.loads(sys.argv[1])
repository = Path(payload.pop("repository"))
payload["parents"] = tuple(payload["parents"])
print("READY", flush=True)
try:
    begin_operation(repository, OperationIntent(**payload))
except Exception as error:
    print(f"{type(error).__name__}: {error}", flush=True)
    raise SystemExit(1)
print("CREATED", flush=True)
"""

_READER = """
import json, sys
from pathlib import Path
from signetum.operation_records import pending_message

payload = json.loads(sys.argv[1])
print("READY", flush=True)
message = pending_message(
    Path(payload["repository"]), payload["branch"], payload["before"], payload["source"]
)
print(json.dumps({"message": message}), flush=True)
"""


def _sync_delivery(repository):
    root, _ = repository
    member = opened(root, "plan/provenance")
    commit_file(member, "own.txt")
    source = commit_file(root, "delivered.txt", "published")
    git_output(root, "push", "origin", "main")
    before = git_output(member, "rev-parse", "HEAD")
    base = read_record(state_root(member), "plan/provenance").base
    result = ops.workspace_sync(member, message=operation_message())
    merge = git_output(member, "rev-parse", "HEAD")
    return root, member, base, before, source, merge, result


def _maintenance(repository, arguments, monkeypatch, capsys):
    monkeypatch.chdir(repository)
    capsys.readouterr()
    code = maintenance.main(arguments)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def _record_document(repository, commit):
    document = records.load_index(repository).for_commit(commit)
    assert document is not None
    return document


def _write_hook(repository, script):
    hook = repository_path(repository, "rev-parse", "--git-path", "hooks") / "commit-msg"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(script, encoding="utf-8")
    hook.chmod(0o755)
    return hook


def test_workspace_sync_binds_the_caller_message_and_exact_objects(repository, monkeypatch, capsys):
    root, member, base, before, source, merge, result = _sync_delivery(repository)
    assert result["status"] == "synchronized"
    assert result["tip"] == merge
    assert records.commit_message(member, merge) == operation_message()
    assert "Signetum-" not in records.commit_message(member, merge)
    document = _record_document(member, merge)
    assert document["kind"] == "member-sync"
    assert document["sync_kind"] == "delivery"
    assert document["status"] == "completed"
    assert document["proof"] == {
        "commit": merge,
        "parents": [before, source],
        "tree": git_output(member, "rev-parse", f"{merge}^{{tree}}"),
    }
    parents = git_output(member, "rev-list", "--parents", "-n", "1", merge).split()[1:]
    assert parents == [before, source]
    assert records.require_bound_commit(member, document)["commit"] == merge
    repeated = ops.workspace_sync(member, message=operation_message())
    assert repeated["tip"] == merge
    assert git_output(member, "rev-parse", "HEAD") == merge
    assert git_output(member, "rev-list", "--count", "--merges", f"{base}..{merge}") == "1"

    message = write_operation_message()
    code, payload, _ = _maintenance(
        member, ["workspace-sync", "--message-file", str(message)], monkeypatch, capsys
    )
    assert code == 0, payload
    assert payload["outcome"] in {"synchronized", "unchanged"}
    assert git_output(root, "rev-parse", "plan/provenance") == merge


def test_message_file_is_rejected_before_any_git_effect(repository, monkeypatch, capsys, tmp_path):
    root, _ = repository
    member = opened(root, "plan/unchecked")
    before = git_output(member, "rev-parse", "HEAD")
    horizon = state_root(member) / "operations" / "legacy-horizon.json"
    assert not horizon.exists()
    cases = {
        "missing.txt": None,
        "blank.txt": b" \n",
        "nul.txt": b"kept\0hidden\n",
        "binary.txt": b"\xff",
    }
    for name, content in cases.items():
        path = tmp_path / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(content)
        code, payload, _ = _maintenance(
            member, ["workspace-sync", "--message-file", str(path)], monkeypatch, capsys
        )
        assert code == 2, payload
        assert git_output(member, "rev-parse", "HEAD") == before
        assert not horizon.exists()
    directory = tmp_path / "messages"
    directory.mkdir()
    code, payload, _ = _maintenance(
        member, ["workspace-sync", "--message-file", str(directory)], monkeypatch, capsys
    )
    assert code == 2, payload
    assert not horizon.exists()


def test_project_hook_rejection_and_rewrite_fail_closed_before_the_merge(repository):
    root, _ = repository
    member = opened(root, "plan/hooked")
    commit_file(member, "own.txt")
    commit_file(root, "delivered.txt", "published")
    git_output(root, "push", "origin", "main")
    before = git_output(member, "rev-parse", "HEAD")
    hook = _write_hook(
        member,
        "#!/bin/sh\necho project commit policy refused >&2\nexit 1\n",
    )
    with pytest.raises(AdmissionError, match="project commit policy refused"):
        ops.workspace_sync(member, message=operation_message())
    assert git_output(member, "rev-parse", "HEAD") == before
    pending = list((state_root(member) / "operations" / "records").glob("*.json"))
    assert len(pending) == 1
    assert json.loads(pending[0].read_text())["status"] == "pending"
    hook.write_text(
        "#!/bin/sh\nprintf '%s\\n' rewritten > \"$1\"\nexit 0\n",
        encoding="utf-8",
    )
    with pytest.raises(AdmissionError, match="changed the recorded message"):
        ops.workspace_sync(member, message=operation_message())
    assert git_output(member, "rev-parse", "HEAD") == before
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    result = ops.workspace_sync(member, message=operation_message())
    merge = git_output(member, "rev-parse", "HEAD")
    assert result["tip"] == merge
    assert records.commit_message(member, merge) == operation_message()
    assert _record_document(member, merge)["status"] == "completed"
    assert git_output(member, "rev-list", "--count", "--merges", f"{before}..{merge}") == "1"
    hook.unlink()


def test_crash_after_the_merge_retries_the_same_commit(repository, monkeypatch):
    root, _ = repository
    member = opened(root, "plan/interrupted")
    commit_file(member, "own.txt")
    commit_file(root, "delivered.txt", "published")
    git_output(root, "push", "origin", "main")

    def explode(*_args, **_kwargs):
        raise AdmissionError("simulated crash after the merge object")

    monkeypatch.setattr(records, "complete_operation", explode)
    with pytest.raises(AdmissionError, match="simulated crash after the merge object"):
        ops.workspace_sync(member, message=operation_message())
    merge = git_output(member, "rev-parse", "HEAD")
    stored = json.loads(
        next((state_root(member) / "operations" / "records").glob("*.json")).read_text()
    )
    assert stored["status"] == "pending"
    assert records.commit_message(member, merge) == operation_message()
    monkeypatch.undo()
    recovered = ops.workspace_sync(member, message=operation_message())
    assert recovered["tip"] == merge
    assert git_output(member, "rev-parse", "HEAD") == merge
    assert _record_document(member, merge)["status"] == "completed"
    assert git_output(member, "rev-list", "--count", "--merges", "HEAD~1..HEAD") == "1"


def test_manual_resolution_binds_one_pending_record(repository):
    root, _ = repository
    member = opened(root, "plan/resolved")
    base = read_record(state_root(member), "plan/resolved").base
    commit_file(member, "seed.txt", "member\n")
    commit_file(root, "seed.txt", "delivery\n")
    git_output(root, "push", "origin", "main")
    with pytest.raises(ops.MergeConflict):
        ops.workspace_sync(member, message=operation_message())
    (member / "seed.txt").write_text("resolved\n")
    git_output(member, "add", "seed.txt")
    git_output(member, "commit", "--no-edit")
    merge = git_output(member, "rev-parse", "HEAD")
    assert records.commit_message(member, merge) == operation_message()
    recovered = ops.workspace_sync(member, message="a different caller message\n")
    assert recovered["tip"] == merge
    assert _record_document(member, merge)["message"] == operation_message()
    assert git_output(member, "rev-list", "--count", "--merges", f"{base}..{merge}") == "1"


def test_forged_missing_and_conflicting_records_fail_closed(repository):
    _root, member, base, _before, source, merge, _result = _sync_delivery(repository)
    document = _record_document(member, merge)
    path = state_root(member) / "operations" / "records" / f"{document['id']}.json"
    original = path.read_text(encoding="utf-8")
    forged = json.loads(original)
    forged["message"] = "forged message\n"
    path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(AdmissionError, match="does not match the Git object"):
        records.require_bound_commit(member, forged)
    path.write_text(original, encoding="utf-8")

    conflict = json.loads(original)
    conflict["id"] = "ab" * 32
    other = path.with_name(f"{conflict['id']}.json")
    other.write_text(json.dumps(conflict), encoding="utf-8")
    with pytest.raises(AdmissionError, match="identity does not match its fields"):
        records.load_index(member)
    other.unlink()

    path.unlink()
    assert verified_syncs(member, base, merge) == ()
    # Without any record the merge reads as history before operations, which
    # grants no base: only exact old-engine text could.
    assert attested_base(member, merge) is None
    assert source not in records.commit_message(member, merge)


def test_copied_trailer_after_the_horizon_is_not_provenance(repository):
    root, member, base, _before, _source, verified, _result = _sync_delivery(repository)
    copied = commit_file(root, "later.txt", "later")
    git_output(root, "push", "origin", "main")
    git_output(member, "fetch", "origin", "main")
    authorize_source(member, base, copied, "delivery")
    git_output(
        member,
        "merge",
        "--no-ff",
        copied,
        "-m",
        f"manual merge\n\nSignetum-Sync: {copied}",
    )
    manual = git_output(member, "rev-parse", "HEAD")
    found = verified_syncs(member, base, manual)
    assert (verified, _source) in found
    assert all(merge != manual for merge, _merged_source in found)
    with pytest.raises(AdmissionError, match="unrecorded merge"):
        attested_base(member, manual)
    assert ops.workspace_sync(member, message=operation_message())["status"] != "recognized"


def test_legacy_merge_before_any_operation_stays_readable(repository):
    root, _ = repository
    member = opened(root, "plan/legacy-sync")
    base = read_record(state_root(member), "plan/legacy-sync").base
    branch = branch_name(member)
    source = commit_file(root, "legacy.txt", "legacy")
    git_output(root, "push", "origin", "main")
    git_output(member, "fetch", "origin", "main")
    authorize_source(member, base, source, "delivery")
    label = "delivery"
    git_output(
        member,
        "merge",
        "--no-ff",
        "FETCH_HEAD",
        "-m",
        f"Merge {label} into {branch}\n\nSignetum-Sync: {source}\nSignetum-Sync-Source: {label}",
    )
    merge = git_output(member, "rev-parse", "HEAD")
    assert not list((state_root(member) / "operations" / "records").glob("*.json"))
    assert records.legacy_commit(member, merge)
    assert verified_syncs(member, base, merge) == ((merge, source),)

    delivered = commit_file(root, "modern.txt", "modern")
    git_output(root, "push", "origin", "main")
    ops.workspace_sync(member, message=operation_message())
    modern = git_output(member, "rev-parse", "HEAD")
    assert records.load_index(member).for_commit(modern) is not None
    copied = commit_file(root, "later.txt", "later")
    git_output(root, "push", "origin", "main")
    git_output(member, "fetch", "origin", "main")
    authorize_source(member, base, copied, "delivery")
    git_output(
        member,
        "merge",
        "--no-ff",
        "FETCH_HEAD",
        "-m",
        f"Merge {label} into {branch}\n\nSignetum-Sync: {copied}\nSignetum-Sync-Source: {label}",
    )
    manual = git_output(member, "rev-parse", "HEAD")
    assert records.legacy_commit(member, merge)
    assert not records.legacy_commit(member, manual)
    found = verified_syncs(member, base, manual)
    assert (merge, source) in found and (modern, delivered) in found
    assert all(item != manual for item, _merged in found)


def test_admission_maps_plans_and_ready_evidence_without_trailers(repository):
    root, _ = repository
    member = ready_member(root, "mapped", "mapped.txt")
    batch = open_batch(root, member)
    tip = git_output(batch, "rev-parse", "HEAD")
    base = read_record(state_root(batch), branch_name(batch)).base
    document = _record_document(batch, tip)
    assert document["kind"] == "admission"
    assert document["plans"] == ["changes/mapped/change.toml"]
    assert "Signetum-" not in records.commit_message(batch, tip)
    assert records.commit_message(batch, tip) == operation_messages(1)[0]
    receipt = lifecycle._receipt_root(member) / str(document["ready_evidence"])
    assert records.qualification_bytes(batch, str(document["ready_evidence_sha256"])) == (
        receipt.read_bytes()
    )
    assert attested_base(batch, tip) == base
    original = receipt.read_bytes()
    receipt.write_bytes(original + b"\n")
    with pytest.raises(AdmissionError, match="ready evidence bytes do not match"):
        execution_review_inputs(
            batch,
            load_manifest(batch / "signetum.toml"),
            base,
            tip,
            lifecycle._receipt_root(member),
        )
    receipt.write_bytes(original)


def test_batch_sync_and_publication_bind_caller_messages(repository):
    root, _ = repository
    batch_a, batch_b = parallel_batches(root)
    published = deliver(root, batch_a)
    landed = git_output(root, "rev-parse", "HEAD")
    assert records.commit_message(root, landed) == operation_message()
    assert "Signetum-" not in records.commit_message(root, landed)
    publication = _record_document(root, landed)
    assert publication["kind"] == "publication"
    assert publication["proof"]["commit"] == published["delivery_commit"]
    assert publication["proof"]["parents"] == [published["base"], published["source"]]
    message = "Synchronize the delivered sibling.\n"
    synced = lifecycle.sync_batch(batch_b, message=message)
    tip = str(synced["batch_commit"])
    assert records.commit_message(batch_b, tip) == message
    assert "Signetum-" not in records.commit_message(batch_b, tip)
    batch_sync = _record_document(batch_b, tip)
    assert batch_sync["kind"] == "batch-sync"
    assert batch_sync["attested_base"] == landed
    assert attested_base(batch_b, tip) == landed


def test_shared_operation_lock_overlap_fails_closed(repository):
    root, _ = repository
    member = opened(root, "plan/contended")
    head = git_output(member, "rev-parse", "HEAD")
    source = commit_file(root, "elsewhere.txt")
    base = read_record(state_root(member), "plan/contended").base
    payload = {
        "repository": str(member),
        "kind": "member-sync",
        "branch": "plan/contended",
        "before": head,
        "source": source,
        "base": base,
        "message": "Contended operation.\n",
        "attested_base": base,
        "parents": [head, source],
        "sync_kind": "delivery",
    }
    intent = records.OperationIntent(
        kind=payload["kind"],
        branch=payload["branch"],
        before=payload["before"],
        source=payload["source"],
        base=payload["base"],
        message=payload["message"],
        attested_base=payload["attested_base"],
        parents=tuple(payload["parents"]),
        sync_kind=payload["sync_kind"],
    )
    operations = state_root(member) / "operations"
    operations.mkdir(parents=True, exist_ok=True)
    handle = (operations / ".lock").open("a+b")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    process = subprocess.Popen(  # noqa: S603 -- owned interpreter, fixture repository only
        [sys.executable, "-c", _CHILD, json.dumps(payload)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "READY"
        assert process.poll() is None
        conflicting = records._intent_document(intent)
        conflicting["message"] = "Different message.\n"
        destination = operations / "records" / f"{intent.identity()}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(records._canonical(conflicting), encoding="utf-8")
        assert process.poll() is None
        handle.close()
        stdout, stderr = process.communicate(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if not handle.closed:
            handle.close()
    assert process.returncode != 0
    assert "conflicts" in stdout + stderr
    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored["message"] == "Different message.\n"


def _intent(member, *, source, message, branch=None):
    head = git_output(member, "rev-parse", "HEAD")
    return records.OperationIntent(
        kind="member-sync",
        branch=branch or branch_name(member),
        before=head,
        source=source,
        base=read_record(state_root(member), branch_name(member)).base,
        message=message,
        attested_base=read_record(state_root(member), branch_name(member)).base,
        parents=(head, source),
        sync_kind="delivery",
    )


def _publish(source, target, base, tip, message):
    return publish_batch(
        source,
        target,
        base,
        tip,
        "main",
        git=git_output,
        remote_tip=lambda repository, branch: git_output(
            repository, "ls-remote", "origin", f"refs/heads/{branch}"
        ).split()[0],
        is_ancestor=is_ancestor,
        message=message,
    )


def _publication_world(repository):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    source = opened(root, "plan/publication")
    tip = commit_file(source, "batch.txt", "published")
    return root, source, base, tip


def test_publication_crash_before_commit_keeps_the_pending_record(repository, monkeypatch):
    root, source, base, tip = _publication_world(repository)
    original = records.create_commit

    def explode(*_args, **_kwargs):
        raise AdmissionError("simulated crash before the publication commit")

    monkeypatch.setattr(records, "create_commit", explode)
    with pytest.raises(AdmissionError, match="simulated crash before the publication commit"):
        _publish(source, root, base, tip, operation_message())
    assert git_output(root, "rev-parse", "HEAD") == base
    assert git_output(root, "ls-remote", "origin", "refs/heads/main").split()[0] == base
    pending = list((state_root(source) / "operations" / "records").glob("*.json"))
    assert len(pending) == 1
    assert json.loads(pending[0].read_text(encoding="utf-8"))["status"] == "pending"
    monkeypatch.setattr(records, "create_commit", original)
    published = _publish(source, root, base, tip, operation_message())
    landed = git_output(root, "rev-parse", "HEAD")
    assert published.commit == landed
    assert git_output(root, "rev-list", "--parents", "-n", "1", landed).split()[1:] == [base, tip]
    assert records.commit_message(root, landed) == operation_message()
    assert git_output(root, "rev-list", "--count", "--merges", f"{base}..{landed}") == "1"


def test_publication_crash_after_commit_reuses_the_same_object(repository, monkeypatch):
    root, source, base, tip = _publication_world(repository)
    original = records.complete_operation
    created = {}

    def explode(_repository, _intent, commit):
        created["commit"] = commit
        raise AdmissionError("simulated crash after the publication object")

    monkeypatch.setattr(records, "complete_operation", explode)
    with pytest.raises(AdmissionError, match="simulated crash after the publication object"):
        _publish(source, root, base, tip, operation_message())
    assert git_output(source, "cat-file", "-t", created["commit"]) == "commit"
    assert git_output(root, "rev-parse", "HEAD") == base
    assert git_output(root, "ls-remote", "origin", "refs/heads/main").split()[0] == base
    monkeypatch.setattr(records, "complete_operation", original)
    published = _publish(source, root, base, tip, operation_message())
    assert published.commit == created["commit"]
    assert git_output(root, "rev-parse", "HEAD") == created["commit"]
    assert _record_document(root, created["commit"])["status"] == "completed"


def test_publication_refuses_unrelated_remotes_and_resumes_its_own_proof(repository, tmp_path):
    root, source, base, tip = _publication_world(repository)
    tree = git_output(source, "rev-parse", f"{tip}^{{tree}}")
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("Unrelated publication.\n", encoding="utf-8")
    other = git_output(source, "commit-tree", tree, "-p", base, "-p", tip, "-F", str(unrelated))
    git_output(source, "push", "origin", f"{other}:refs/heads/main")
    with pytest.raises(AdmissionError, match="remote publication has no matching operation proof"):
        _publish(source, root, base, tip, operation_message())
    assert git_output(root, "rev-parse", "HEAD") == base
    assert not list((state_root(root) / "operations" / "records").glob("*.json"))
    git_output(source, "push", "--force", "origin", f"{base}:refs/heads/main")

    git_output(source, "push", "--force", "origin", f"{base}:refs/heads/main")
    git_output(root, "reset", "--keep", base)
    published = _publish(source, root, base, tip, operation_message())
    landed = published.commit
    with pytest.raises(AdmissionError, match="remote publication has no matching operation proof"):
        _publish(source, root, base, tip, "A different publication message.\n")
    assert git_output(root, "rev-parse", "HEAD") == landed
    assert records.commit_message(root, landed) == operation_message()
    assert git_output(root, "rev-list", "--count", "--merges", f"{base}..{landed}") == "1"

    git_output(root, "reset", "--keep", base)
    again = _publish(source, root, base, tip, operation_message())
    assert again.commit == landed
    assert git_output(root, "rev-parse", "HEAD") == landed

    git_output(root, "reset", "--keep", base)
    commit_file(root, "diverged.txt", "diverged")
    with pytest.raises(AdmissionError, match="target tip differs"):
        _publish(source, root, base, tip, operation_message())
    assert git_output(root, "rev-list", "--count", "--merges", "HEAD") == "0"

    same = tmp_path / "same.txt"
    same.write_text(operation_message(), encoding="utf-8")
    conflicting = git_output(
        source,
        "-c",
        "user.name=Conflicting publisher",
        "commit-tree",
        tree,
        "-p",
        base,
        "-p",
        tip,
        "-F",
        str(same),
    )
    assert conflicting != landed
    git_output(root, "reset", "--keep", base)
    git_output(source, "push", "--force", "origin", f"{conflicting}:refs/heads/main")
    with pytest.raises(AdmissionError, match="completed operation proof conflicts"):
        _publish(source, root, base, tip, operation_message())
    assert git_output(root, "rev-parse", "HEAD") == base


def test_completed_sync_outside_head_does_not_authorize_another_merge(repository):
    _root, member, base, before, _source, merge, _result = _sync_delivery(repository)
    git_output(member, "reset", "--keep", before)
    recovered = ops.workspace_sync(member, message="another message\n")
    assert recovered["tip"] == merge
    assert git_output(member, "rev-parse", "HEAD") == merge
    assert records.commit_message(member, merge) == operation_message()
    assert git_output(member, "rev-list", "--count", "--merges", f"{base}..{merge}") == "1"

    git_output(member, "reset", "--keep", before)
    side = commit_file(member, "side.txt", "side")
    with pytest.raises(AdmissionError, match="not on the branch"):
        ops.workspace_sync(member, message=operation_message())
    assert git_output(member, "rev-parse", "HEAD") == side
    assert git_output(member, "rev-list", "--count", "--merges", f"{base}..{side}") == "0"
    assert _record_document(member, merge)["status"] == "completed"


def test_member_sync_crash_before_the_merge_retries_the_pending_record(repository, monkeypatch):
    root, _ = repository
    member = opened(root, "plan/merge-crash")
    commit_file(member, "own.txt")
    commit_file(root, "delivered.txt", "published")
    git_output(root, "push", "origin", "main")
    before = git_output(member, "rev-parse", "HEAD")
    original = records.run_git

    def fail_merge(repository_path, *arguments, **kwargs):
        if "merge" in arguments:
            raise AdmissionError("simulated crash before the merge")
        return original(repository_path, *arguments, **kwargs)

    monkeypatch.setattr(records, "run_git", fail_merge)
    with pytest.raises(AdmissionError, match="simulated crash before the merge"):
        ops.workspace_sync(member, message=operation_message())
    assert git_output(member, "rev-parse", "HEAD") == before
    assert run_merge_head(member) is False
    pending = list((state_root(member) / "operations" / "records").glob("*.json"))
    assert len(pending) == 1
    assert json.loads(pending[0].read_text(encoding="utf-8"))["status"] == "pending"
    monkeypatch.setattr(records, "run_git", original)
    recovered = ops.workspace_sync(member, message=operation_message())
    merge = git_output(member, "rev-parse", "HEAD")
    assert recovered["tip"] == merge
    assert records.commit_message(member, merge) == operation_message()
    assert git_output(member, "rev-list", "--count", "--merges", f"{before}..{merge}") == "1"


def test_a_different_pending_operation_on_one_branch_fails_closed(repository):
    root, _ = repository
    member = opened(root, "plan/one-live")
    first = commit_file(root, "first-source.txt")
    second = commit_file(root, "second-source.txt")
    head = git_output(member, "rev-parse", "HEAD")
    records.begin_operation(member, _intent(member, source=first, message="First effect.\n"))
    with pytest.raises(AdmissionError, match="another operation is already pending"):
        records.begin_operation(member, _intent(member, source=second, message="Second effect.\n"))
    assert git_output(member, "rev-parse", "HEAD") == head
    records_dir = state_root(member) / "operations" / "records"
    assert len(list(records_dir.glob("*.json"))) == 1


def test_pending_reader_does_not_deadlock_behind_a_competing_begin(repository):
    root, _ = repository
    member = opened(root, "plan/barrier")
    first = commit_file(root, "barrier-first.txt")
    second = commit_file(root, "barrier-second.txt")
    held = _intent(member, source=first, message="Held operation.\n")
    competing = _intent(member, source=second, message="Competing operation.\n")
    operations = state_root(member) / "operations"
    operations.mkdir(parents=True, exist_ok=True)
    handle = (operations / ".lock").open("a+b")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    payload = {
        "repository": str(member),
        "kind": competing.kind,
        "branch": competing.branch,
        "before": competing.before,
        "source": competing.source,
        "base": competing.base,
        "message": competing.message,
        "attested_base": competing.attested_base,
        "parents": list(competing.parents),
        "sync_kind": competing.sync_kind,
    }
    beginner = subprocess.Popen(  # noqa: S603 -- owned interpreter, fixture repository only
        [sys.executable, "-c", _CHILD, json.dumps(payload)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    reader = subprocess.Popen(  # noqa: S603 -- owned interpreter, fixture repository only
        [
            sys.executable,
            "-c",
            _READER,
            json.dumps(
                {
                    "repository": str(member),
                    "branch": held.branch,
                    "before": held.before,
                    "source": held.source,
                }
            ),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert beginner.stdout is not None and reader.stdout is not None
        assert beginner.stdout.readline().strip() == "READY"
        assert reader.stdout.readline().strip() == "READY"
        assert beginner.poll() is None
        assert reader.poll() is None
        destination = operations / "records" / f"{held.identity()}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(records._canonical(records._intent_document(held)), encoding="utf-8")
        assert beginner.poll() is None
        assert reader.poll() is None
        handle.close()
        begin_out, begin_err = beginner.communicate(timeout=30)
        read_out, read_err = reader.communicate(timeout=30)
    finally:
        for process in (beginner, reader):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        if not handle.closed:
            handle.close()
    assert beginner.returncode != 0
    assert "another operation is already pending" in begin_out + begin_err
    assert reader.returncode == 0, read_out + read_err
    assert json.loads(read_out.splitlines()[-1])["message"] == "Held operation.\n"
    assert git_output(member, "rev-parse", "HEAD") == held.before


def run_merge_head(repository):
    completed = git_output(repository, "rev-parse", "--verify", "MERGE_HEAD", check=False)
    return bool(completed)


def test_index_reads_parse_records_without_consulting_git(repository, monkeypatch):
    _root, member, _base, _before, _source, merge, _result = _sync_delivery(repository)

    def refuse(*_args, **_kwargs):
        raise AssertionError("an index read consulted Git")

    monkeypatch.setattr(records, "run_git", refuse)
    monkeypatch.setattr(records, "git_output", refuse)
    assert records.load_index(member).for_commit(merge) is not None
