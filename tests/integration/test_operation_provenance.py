"""Real Git proof for structured operation records.

Retained legacy and authorization coverage stays in the existing modules.
This module replaces superseded trailer assertions with exact message and
object checks, and adds read-only history plus already-pending old proofs.
"""

import fcntl
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from operation_messages import operation_message, operation_messages, write_operation_message
from signetum import lifecycle, maintenance
from signetum import operation_records as records
from signetum import workspace_operations as ops
from signetum.commit_check import install_commit_check
from signetum.delivery import publish_batch
from signetum.execution_review import execution_review_inputs
from signetum.gate_records import record_pending_admissions
from signetum.git import git_output, repository_path
from signetum.manifest import load_manifest
from signetum.operations import AdmissionError
from signetum.provenance import attested_base
from signetum.stacking import is_ancestor
from signetum.synchronization import authorize_source, prepare_merge, verified_syncs
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
    with pytest.raises(AdmissionError, match="conflicting operation proofs"):
        records.load_index(member)
    other.unlink()

    path.unlink()
    assert verified_syncs(member, base, merge) == ()
    with pytest.raises(AdmissionError, match="unrecorded merge"):
        attested_base(member, merge)
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


def test_legacy_merge_inside_the_horizon_stays_readable(repository):
    root, _ = repository
    member = opened(root, "plan/legacy-sync")
    base = read_record(state_root(member), "plan/legacy-sync").base
    branch = branch_name(member)
    source = commit_file(root, "legacy.txt", "legacy")
    git_output(root, "push", "origin", "main")
    git_output(member, "fetch", "origin", "main")
    horizon_path = state_root(member) / "operations" / "legacy-horizon.json"
    assert not horizon_path.exists()
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
    assert verified_syncs(member, base, merge) == ()
    horizon = json.loads(horizon_path.read_text(encoding="utf-8"))
    assert horizon["adopted"] is False
    assert horizon["tips"] == {}
    assert not list((state_root(member) / "operations" / "records").glob("*.json"))

    records.adopt_legacy_history(member, [merge])
    assert verified_syncs(member, base, merge) == ((merge, source),)
    assert records.legacy_commit(member, merge)
    assert not list((state_root(member) / "operations" / "records").glob("*.json"))

    copied = commit_file(root, "later.txt", "later")
    git_output(root, "push", "origin", "main")
    git_output(member, "fetch", "origin", "main")
    git_output(member, "merge", "--no-ff", "FETCH_HEAD", "-m", f"manual\n\nSignetum-Sync: {copied}")
    manual = git_output(member, "rev-parse", "HEAD")
    found = verified_syncs(member, base, manual)
    assert (merge, source) in found
    assert all(item != manual for item, _merged in found)
    with pytest.raises(AdmissionError, match="cannot expand"):
        records.adopt_legacy_history(member, [manual])
    assert not records.legacy_commit(member, manual)


def test_published_history_adopts_without_granting_new_provenance(repository, tmp_path):
    del repository
    published = "75ed8fd577c6d5422b295de9b6358e12e5ca5d4c"
    origin = Path(__file__).resolve().parents[2]
    checkout = tmp_path / "published-history"
    git_output(
        origin,
        "clone",
        "--shared",
        "--no-checkout",
        "--branch",
        "main",
        str(origin),
        str(checkout),
    )
    adopted = records.adopt_legacy_history(checkout, [published])
    assert adopted["adopted"] is True
    assert records.legacy_commit(checkout, published)
    roots = git_output(checkout, "rev-list", "--max-parents=0", published).splitlines()
    assert roots
    assert all(records.legacy_commit(checkout, commit) for commit in roots)
    attested_base(checkout, published)


def test_pre_protocol_ancestry_is_readable_and_import_cannot_cut_over(repository, tmp_path):
    root, _ = repository
    member = opened(root, "plan/pre-protocol")
    base = read_record(state_root(member), "plan/pre-protocol").base
    parent = git_output(root, "rev-parse", "HEAD")
    side = tmp_path / "side"
    git_output(root, "worktree", "add", "-b", "side", str(side), parent)
    source = commit_file(side, "ancestor.txt", "ancestor")
    commit_file(member, "own.txt", "own")
    git_output(
        member,
        "merge",
        "--no-ff",
        source,
        "-m",
        f"ordinary ancestry\n\nSignetum-Sync: {source}\nSignetum-Batch-Base: {base}\n",
    )
    merge = git_output(member, "rev-parse", "HEAD")
    records.adopt_legacy_history(member, [merge])
    assert records.legacy_commit(member, merge)
    assert records.legacy_commit(member, parent)
    assert attested_base(member, merge) is None
    authorize_source(member, base, source, "delivery")
    assert all(item != merge for item, _merged in verified_syncs(member, base, merge))
    commit_file(member, "after.txt", "after")
    with pytest.raises(AdmissionError, match="cannot expand"):
        records.adopt_legacy_history(member, ["HEAD"])
    assert not records.legacy_commit(member, git_output(member, "rev-parse", "HEAD"))

    fresh = _clone(root, tmp_path / "fresh-cutover")
    # The member merge is not on the clone's main branch until a ref can see it.
    git_output(fresh, "update-ref", "refs/heads/observed", merge)
    horizon = {
        "schema_version": records.SCHEMA_VERSION,
        "adopted": True,
        "tips": {"refs/heads/observed": merge},
        "pending_merges": [],
        "sync_record_sha256": [],
    }
    payload = {
        "schema_version": records.SCHEMA_VERSION,
        "operations": [],
        "qualifications": [],
        "legacy_horizon": horizon,
    }
    with pytest.raises(AdmissionError, match="cannot establish a cutover"):
        records.import_operations(fresh, payload)
    assert records.legacy_commit(fresh, merge) is False
    with pytest.raises(AdmissionError, match="unrecorded merge"):
        attested_base(fresh, merge)

    records.adopt_legacy_history(fresh, [merge])
    assert records.import_operations(fresh, payload)["status"] == "imported"
    assert records.legacy_commit(fresh, merge)

    tree = git_output(root, "rev-parse", f"{parent}^{{tree}}")
    message = tmp_path / "orphan.txt"
    message.write_text("unrelated history\n", encoding="utf-8")
    orphan = git_output(root, "commit-tree", tree, "-F", str(message))
    git_output(fresh, "update-ref", "refs/heads/orphan", orphan)
    conflict = json.loads(json.dumps(payload))
    conflict["legacy_horizon"]["tips"] = {"refs/heads/observed": orphan}
    with pytest.raises(AdmissionError, match="cannot expand"):
        records.import_operations(fresh, conflict)
    assert records.legacy_commit(fresh, merge)
    assert records.legacy_commit(fresh, orphan) is False


def test_legacy_pending_merge_completes_under_its_snapshot(repository):
    root, _ = repository
    member = opened(root, "plan/legacy-pending")
    base = read_record(state_root(member), "plan/legacy-pending").base
    source = commit_file(root, "pending.txt", "pending")
    git_output(root, "push", "origin", "main")
    git_output(member, "fetch", "origin", "main")
    before = git_output(member, "rev-parse", "HEAD")
    git_output(member, "merge", "--no-ff", "--no-commit", "FETCH_HEAD")
    message = f"record delivery\n\nSignetum-Sync: {source}\n"
    repository_path(member, "rev-parse", "--git-path", "MERGE_MSG").write_text(
        message, encoding="utf-8"
    )
    authorize_source(member, base, source, "delivery")
    prepare_merge(member, source, message)
    assert not (state_root(member) / "operations" / "legacy-horizon.json").exists()
    records.load_index(member)
    horizon = json.loads(
        (state_root(member) / "operations" / "legacy-horizon.json").read_text(encoding="utf-8")
    )
    assert {"before": before, "source": source, "trailers": [f"Signetum-Sync: {source}"]} in (
        horizon["pending_merges"]
    )
    git_output(member, "commit", "--no-edit")
    merge = git_output(member, "rev-parse", "HEAD")
    assert records.legacy_pending_commit(member, merge)
    assert verified_syncs(member, base, merge) == ((merge, source),)
    assert not records.legacy_commit(member, merge)


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


def test_export_import_round_trip_is_idempotent_and_refuses_bad_proof(
    repository, monkeypatch, capsys, tmp_path
):
    root, member, base, _before, source, merge, _result = _sync_delivery(repository)
    proof = tmp_path / "operations.json"
    code, payload, _ = _maintenance(
        member,
        ["operation-export", "--from", base, "--to", merge, "--output", str(proof)],
        monkeypatch,
        capsys,
    )
    assert code == 0, payload
    assert payload["outcome"] == "exported"
    assert payload["operations"] == 1
    exported = proof.read_text(encoding="utf-8")
    assert str(tmp_path) not in exported
    assert "/Users/" not in exported
    assert "~/" not in exported
    checkout = tmp_path / "independent"
    git_output(root, "clone", "--shared", str(root), str(checkout))
    assert state_root(checkout) != state_root(member)
    code, payload, _ = _maintenance(
        checkout, ["operation-import", "--input", str(proof)], monkeypatch, capsys
    )
    assert code == 0, payload
    assert payload["outcome"] == "imported"
    imported = _record_document(checkout, merge)
    assert imported["proof"]["parents"] == [imported["before"], source]
    assert verified_syncs(checkout, base, merge) == ((merge, source),)
    record_path = state_root(checkout) / "operations" / "records" / f"{imported['id']}.json"
    stored = record_path.read_bytes()
    code, payload, _ = _maintenance(
        checkout, ["operation-import", "--input", str(proof)], monkeypatch, capsys
    )
    assert code == 0, payload
    assert record_path.read_bytes() == stored

    tampered = json.loads(exported)
    tampered["operations"][0]["message"] = "tampered message\n"
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    code, payload, _ = _maintenance(
        checkout, ["operation-import", "--input", str(tampered_path)], monkeypatch, capsys
    )
    assert code == 2, payload
    assert "message" in payload["cause"]
    assert record_path.read_bytes() == stored

    record_path.write_text(stored.decode().replace(operation_message().strip(), "local edit"))
    local = record_path.read_bytes()
    code, payload, _ = _maintenance(
        checkout, ["operation-import", "--input", str(proof)], monkeypatch, capsys
    )
    assert code == 2, payload
    assert "conflict" in payload["cause"]
    assert record_path.read_bytes() == local

    empty = tmp_path / "empty"
    empty.mkdir()
    git_output(empty, "init", "-b", "main")
    code, payload, _ = _maintenance(
        empty, ["operation-import", "--input", str(proof)], monkeypatch, capsys
    )
    assert code == 2, payload
    assert "not in this repository" in payload["cause"]
    assert not list((state_root(empty) / "operations" / "records").glob("*.json"))

    foreign = json.loads(exported)
    foreign["operations"][0]["proof"]["commit"] = base
    foreign_path = tmp_path / "foreign.json"
    foreign_path.write_text(json.dumps(foreign), encoding="utf-8")
    bare = tmp_path / "foreign-checkout"
    git_output(root, "clone", "--shared", str(root), str(bare))
    code, payload, _ = _maintenance(
        bare, ["operation-import", "--input", str(foreign_path)], monkeypatch, capsys
    )
    assert code == 2, payload
    assert not list((state_root(bare) / "operations" / "records").glob("*.json"))


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


def _clone(root, destination):
    git_output(root, "clone", "--shared", str(root), str(destination))
    return destination


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


def _legacy_admission_message(batch, member):
    member_branch = branch_name(member)
    member_tip = git_output(member, "rev-parse", "HEAD")
    batch_base = read_record(state_root(batch), branch_name(batch)).base
    manifest = load_manifest(member / "signetum.toml")
    evidence = lifecycle._admission_evidence(member, member_tip, manifest)
    patch = lifecycle._stable_patch_id(member, batch_base, member_tip)
    text = "\n".join(
        (
            f"Merge {member_branch} into integration batch",
            "",
            f"Signetum-Base: {batch_base}",
            f"Signetum-Original: {member_tip}",
            f"Signetum-Member: {member_branch}",
            f"Signetum-Batch-Base: {batch_base}",
            f"Signetum-Patch-ID: {patch}",
            f"Signetum-Ready-Evidence: {evidence}",
        )
    )
    frozen = records.freeze_message(text)
    assert records._legacy_merge_message(frozen)
    return frozen, member_tip


def test_import_rejects_inconsistent_identity_and_proof(repository, tmp_path):
    root, member, base, _before, source, merge, _result = _sync_delivery(repository)
    document = records.export_operations(member, base, merge)
    clone = _clone(root, tmp_path / "forged")
    forged = json.loads(json.dumps(document))
    item = forged["operations"][0]
    item["source"] = item["before"]
    item["parents"] = [item["source"], item["before"]]
    item["id"] = records.intent_from_document(item).identity()
    item["parents"] = list(item["proof"]["parents"])
    item["before"] = item["proof"]["parents"][0]
    item["id"] = records.intent_from_document(item).identity()
    with pytest.raises(AdmissionError, match="operation source is not its second parent"):
        records.import_operations(clone, forged)
    assert not list((state_root(clone) / "operations" / "records").glob("*.json"))

    found = records.load_index(member).for_commit(merge)
    assert found is not None
    parents = found["parents"]
    assert isinstance(parents, list)
    reversed_parents = list(reversed(parents))
    assert reversed_parents
    first_parent = reversed_parents[0]
    assert isinstance(first_parent, str)
    loaded = dict(found)
    loaded["parents"] = reversed_parents
    loaded["before"] = first_parent
    loaded["attested_base"] = source
    with pytest.raises(AdmissionError, match="operation parents do not match its proof"):
        records.require_bound_commit(member, loaded)


def test_import_rejects_duplicate_commits_and_malformed_records(repository, tmp_path):
    root, member, base, _before, _source, merge, _result = _sync_delivery(repository)
    document = records.export_operations(member, base, merge)
    bundle = json.loads(json.dumps(document))
    extra = json.loads(json.dumps(bundle["operations"][0]))
    extra["branch"] = "plan/other-claim"
    extra["id"] = records.intent_from_document(extra).identity()
    bundle["operations"].append(extra)
    fresh = _clone(root, tmp_path / "bundle")
    with pytest.raises(AdmissionError, match="conflicting operation proofs claim one commit"):
        records.import_operations(fresh, bundle)
    assert not list((state_root(fresh) / "operations" / "records").glob("*.json"))

    checkout = _clone(root, tmp_path / "once")
    assert records.import_operations(checkout, document)["status"] == "imported"
    imported = records.load_index(checkout).for_commit(merge)
    assert imported is not None
    identity = imported["id"]
    assert isinstance(identity, str)
    record_path = state_root(checkout) / "operations" / "records" / f"{identity}.json"
    stored = record_path.read_bytes()
    second = json.loads(json.dumps(document))
    second["operations"][0]["branch"] = "plan/other-claim"
    second["operations"][0]["id"] = records.intent_from_document(second["operations"][0]).identity()
    with pytest.raises(AdmissionError, match="conflicting operation proofs claim one commit"):
        records.import_operations(checkout, second)
    assert record_path.read_bytes() == stored
    other_path = record_path.with_name(f"{second['operations'][0]['id']}.json")
    assert not other_path.exists()

    missing = json.loads(json.dumps(document))
    del missing["operations"][0]["mappings"]
    bare = _clone(root, tmp_path / "missing")
    with pytest.raises(AdmissionError, match="operation mappings are invalid"):
        records.import_operations(bare, missing)
    assert not list((state_root(bare) / "operations" / "records").glob("*.json"))

    unknown = json.loads(json.dumps(document))
    unknown["operations"][0]["note"] = "not a proof field"
    unknown_clone = _clone(root, tmp_path / "unknown")
    with pytest.raises(AdmissionError, match="unknown fields"):
        records.import_operations(unknown_clone, unknown)
    assert not list((state_root(unknown_clone) / "operations" / "records").glob("*.json"))


def test_import_rejects_horizon_that_is_not_legacy_evidence(repository, tmp_path):
    root, member, base, _before, source, merge, _result = _sync_delivery(repository)
    document = records.export_operations(member, base, merge)

    foreign = json.loads(json.dumps(document))
    foreign["legacy_horizon"]["adopted"] = True
    foreign["legacy_horizon"]["tips"] = {"refs/heads/main": "ab" * 20}
    foreign_clone = _clone(root, tmp_path / "foreign-tip")
    with pytest.raises(AdmissionError, match="operation object is unavailable"):
        records.import_operations(foreign_clone, foreign)
    assert not (state_root(foreign_clone) / "operations" / "legacy-horizon.json").exists()

    pending = json.loads(json.dumps(document))
    pending["legacy_horizon"]["pending_merges"] = [
        {"before": base, "source": source, "trailers": [f"Signetum-Sync: {source}"]}
    ]
    pending_clone = _clone(root, tmp_path / "pending")
    with pytest.raises(AdmissionError, match="imported legacy merge is not evidenced"):
        records.import_operations(pending_clone, pending)
    assert not list((state_root(pending_clone) / "operations" / "records").glob("*.json"))

    digested = json.loads(json.dumps(document))
    digested["legacy_horizon"]["sync_record_sha256"] = ["ab" * 32]
    digest_clone = _clone(root, tmp_path / "digest")
    with pytest.raises(AdmissionError, match="imported sync evidence is not in this repository"):
        records.import_operations(digest_clone, digested)

    modern = json.loads(json.dumps(document))
    modern["legacy_horizon"]["adopted"] = True
    modern["legacy_horizon"]["tips"] = {"refs/heads/main": merge}
    modern_clone = _clone(root, tmp_path / "modern")
    # The shared clone has the object, but no local branch can see the member merge yet.
    git_output(modern_clone, "update-ref", "refs/heads/observed", merge)
    with pytest.raises(
        AdmissionError, match="legacy adoption cannot include a structured operation"
    ):
        records.import_operations(modern_clone, modern)
    assert not list((state_root(modern_clone) / "operations" / "records").glob("*.json"))
    assert not (state_root(modern_clone) / "operations" / "legacy-horizon.json").exists()

    initial = git_output(root, "rev-list", "--max-parents=0", "HEAD")
    records.adopt_legacy_history(root, [initial])
    commit_file(root, "after-cutover.txt", "later")
    with pytest.raises(AdmissionError, match="cannot expand"):
        records.adopt_legacy_history(root, ["HEAD"])

    later = commit_file(root, "after-record.txt", "after")
    git_output(root, "push", "origin", "main")
    git_output(member, "fetch", "origin", "main")
    git_output(
        member,
        "merge",
        "--no-ff",
        "FETCH_HEAD",
        "-m",
        f"manual\n\nSignetum-Sync: {later}\n",
    )
    descendant = git_output(member, "rev-parse", "HEAD")
    with pytest.raises(AdmissionError, match="structured operation"):
        records.adopt_legacy_history(member, [descendant])
    assert not records.legacy_commit(member, descendant)
    with pytest.raises(AdmissionError, match="unrecorded merge"):
        attested_base(member, descendant)


def test_imported_qualification_must_match_the_admission_bytes(repository, tmp_path):
    root, _ = repository
    member = ready_member(root, "qualified", "qualified.txt")
    batch = open_batch(root, member)
    base = read_record(state_root(batch), branch_name(batch)).base
    tip = git_output(batch, "rev-parse", "HEAD")
    document = records.export_operations(batch, base, tip)
    qualifications = document["qualifications"]
    assert isinstance(qualifications, list) and qualifications
    qualification = qualifications[0]
    assert isinstance(qualification, dict)
    digest = qualification["sha256"]
    assert isinstance(digest, str)
    original = (state_root(batch) / "operations" / "qualifications" / digest).read_bytes()
    clone = _clone(root, tmp_path / "qualified")
    assert records.import_operations(clone, document)["status"] == "imported"
    assert (state_root(clone) / "operations" / "qualifications" / digest).read_bytes() == original

    tampered = json.loads(json.dumps(document))
    tampered["qualifications"][0]["content"] = "tampered qualification\n"
    refused = _clone(root, tmp_path / "tampered")
    with pytest.raises(AdmissionError, match="do not match their digest"):
        records.import_operations(refused, tampered)
    assert not list((state_root(refused) / "operations" / "records").glob("*.json"))
    assert (state_root(batch) / "operations" / "qualifications" / digest).read_bytes() == original

    absent = json.loads(json.dumps(document))
    absent["qualifications"] = []
    bare = _clone(root, tmp_path / "absent-qualification")
    with pytest.raises(AdmissionError, match="exported qualification bytes are missing"):
        records.import_operations(bare, absent)
    assert not list((state_root(bare) / "operations" / "records").glob("*.json"))

    other = ready_member(root, "unrelated", "unrelated.txt")
    other_tip = git_output(other, "rev-parse", "HEAD")
    foreign_bytes = None
    foreign_name = ""
    for path in lifecycle._receipt_root(root).glob("*-lifecycle-*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence = payload.get("evidence")
        if isinstance(evidence, dict) and evidence.get("identity", {}).get("commit") == other_tip:
            foreign_bytes = path.read_bytes()
            foreign_name = path.name
            break
    assert foreign_bytes is not None
    foreign_digest = hashlib.sha256(foreign_bytes).hexdigest()
    replaced = json.loads(json.dumps(document))
    replaced["qualifications"] = [
        {"sha256": foreign_digest, "content": foreign_bytes.decode("utf-8")}
    ]
    replaced["operations"][0]["ready_evidence"] = foreign_name
    replaced["operations"][0]["ready_evidence_sha256"] = foreign_digest
    replaced["operations"][0]["id"] = records.intent_from_document(
        replaced["operations"][0]
    ).identity()
    substituted = _clone(root, tmp_path / "substituted-qualification")
    with pytest.raises(AdmissionError, match="does not bind its source"):
        records.import_operations(substituted, replaced)
    assert not (state_root(substituted) / "operations" / "qualifications" / foreign_digest).exists()
    assert not list((state_root(substituted) / "operations" / "records").glob("*.json"))

    def _reidentified(change: dict[str, object]) -> dict[str, object]:
        forged = json.loads(json.dumps(document))
        forged["operations"][0].update(change)
        forged["operations"][0]["id"] = records.intent_from_document(
            forged["operations"][0]
        ).identity()
        return forged

    replanned = _clone(root, tmp_path / "replanned")
    with pytest.raises(AdmissionError, match="plans do not match the approved source"):
        records.import_operations(
            replanned, _reidentified({"plans": ["changes/unrelated/change.toml"]})
        )
    assert not list((state_root(replanned) / "operations" / "qualifications").glob("*"))
    assert not list((state_root(replanned) / "operations" / "records").glob("*.json"))

    repatched = _clone(root, tmp_path / "repatched")
    with pytest.raises(AdmissionError, match="patch does not match the approved source"):
        records.import_operations(repatched, _reidentified({"patch_id": "ab" * 20}))
    assert not list((state_root(repatched) / "operations" / "qualifications").glob("*"))
    assert not list((state_root(repatched) / "operations" / "records").glob("*.json"))


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


def test_publication_refuses_unrelated_remotes_and_resumes_legacy_proof(repository, tmp_path):
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

    legacy_path = tmp_path / "legacy.txt"
    legacy_path.write_text(
        records.legacy_publication_message("reviewed", "main", base, tip), encoding="utf-8"
    )
    legacy = git_output(source, "commit-tree", tree, "-p", base, "-p", tip, "-F", str(legacy_path))
    git_output(source, "branch", "legacy-publication", legacy)
    records.adopt_legacy_history(source, [legacy])
    git_output(source, "push", "--force", "origin", f"{legacy}:refs/heads/main")
    resumed = _publish(source, root, base, tip, operation_message())
    assert resumed.commit == legacy
    assert git_output(root, "rev-parse", "HEAD") == legacy
    assert records.load_index(root).for_commit(legacy) is None
    assert records.commit_message(root, legacy).startswith("Merge reviewed into main\n")

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
    conflicting = git_output(source, "commit-tree", tree, "-p", base, "-p", tip, "-F", str(same))
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


def test_legacy_admission_continuation_accepts_messages_for_remaining_members(
    repository, monkeypatch
):
    root, _ = repository
    first = ready_member(root, "legacy-first", "first.txt")
    second = ready_member(root, "legacy-second", "second.txt")
    base = git_output(root, "rev-parse", "HEAD")
    batch = Path(str(ops.open_workspace(root, "batch/legacy-wave", base, kind="batch")["worktree"]))
    message, member_tip = _legacy_admission_message(batch, first)
    git_output(batch, "merge", "--no-ff", "--no-commit", member_tip)
    repository_path(batch, "rev-parse", "--git-path", "MERGE_MSG").write_text(
        message, encoding="utf-8"
    )
    prepare_merge(batch, member_tip, message)
    record_pending_admissions(batch, branch_name(batch), (second,))
    horizon_path = state_root(batch) / "operations" / "legacy-horizon.json"
    if horizon_path.is_file():
        horizon = json.loads(horizon_path.read_text(encoding="utf-8"))
        assert horizon.get("adopted") is False
        assert horizon.get("tips") == {}
        assert horizon.get("pending_merges") == []
        horizon_path.unlink()
    before = git_output(batch, "rev-parse", "HEAD")
    with pytest.raises(AdmissionError, match="missing frozen messages"):
        lifecycle.continue_batch(batch)
    assert git_output(batch, "rev-parse", "HEAD") == before
    assert run_merge_head(batch)
    original = lifecycle.create_commit

    def explode(*_args, **_kwargs):
        raise AdmissionError("simulated crash before the legacy resolution commit")

    monkeypatch.setattr(lifecycle, "create_commit", explode)
    remaining = operation_messages(1)
    with pytest.raises(AdmissionError, match="simulated crash before the legacy resolution commit"):
        lifecycle.continue_batch(batch, messages=remaining)
    assert git_output(batch, "rev-parse", "HEAD") == before
    assert run_merge_head(batch)
    stored = json.loads(horizon_path.read_text(encoding="utf-8"))
    pending = stored["pending_merges"]
    assert pending[0]["continuation_messages"] == list(remaining)
    assert install_commit_check(batch)["status"] == "active"
    monkeypatch.setattr(lifecycle, "create_commit", original)
    result = lifecycle.continue_batch(batch, messages=remaining)
    merge = str(result["admission_commit"])
    assert git_output(batch, "rev-parse", "HEAD^{}") != before
    assert records.commit_message(batch, merge) == message
    assert "batch resolution" not in records.commit_message(batch, merge)
    assert "Signetum-Member:" in records.commit_message(batch, merge)
    assert records.load_index(batch).for_commit(merge) is None
    assert (batch / "first.txt").is_file()
    assert (batch / "second.txt").is_file()
    resumed = result["resumed_admission"]
    assert isinstance(resumed, dict)
    admitted = resumed["admitted"]
    assert isinstance(admitted, list)
    branches: list[object] = []
    for item in admitted:
        assert isinstance(item, dict)
        branches.append(item["branch"])
    assert branches == ["change/legacy-second"]
    modern = _record_document(batch, git_output(batch, "rev-parse", "HEAD"))
    assert modern["kind"] == "admission"
    assert modern["message"] == remaining[0]
    assert "Signetum-" not in modern["message"]


def run_merge_head(repository):
    completed = git_output(repository, "rev-parse", "--verify", "MERGE_HEAD", check=False)
    return bool(completed)
