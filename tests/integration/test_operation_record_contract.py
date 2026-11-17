"""A stored operation record is parsed on read and judged against Git on write and use."""

import pytest
from signetum import operation_records as records
from signetum.git import git_output
from signetum.operations import AdmissionError
from signetum.provenance import members_and_plans
from test_batch_synchronization import open_batch, ready_member

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # pragma: allowlist secret


@pytest.fixture
def admitted(repository):
    root, _ = repository
    member = ready_member(root, "contract", "contract.txt")
    batch = open_batch(root, member)
    commit = git_output(batch, "rev-parse", "HEAD")
    document = records.load_index(batch).for_commit(commit)
    assert document is not None and document["kind"] == "admission"
    git_output(batch, "hash-object", "-w", "-t", "tree", "/dev/null")
    orphan = git_output(batch, "commit-tree", EMPTY_TREE, "-m", "unrelated history")
    return batch, dict(document), orphan


def test_the_stored_admission_parses_and_binds(admitted):
    batch, document, _ = admitted
    assert records.parse_operation(document) == document
    assert records.require_bound_commit(batch, document) == document["proof"]


def test_a_malformed_record_is_refused_when_read(admitted):
    _, document, _ = admitted
    before, source = document["before"], document["source"]
    cases = [
        ([], "operation record is malformed"),
        ({**document, "extra": 1}, "unknown fields: extra"),
        ({**document, "schema_version": 2}, "schema is unsupported"),
        ({**document, "schema_version": True}, "schema is unsupported"),
        ({**document, "kind": "rebase"}, "operation kind is invalid"),
        ({**document, "status": "aborted"}, "operation status is invalid"),
        ({**document, "base": "abc"}, "base is not a commit id"),
        ({**document, "tree": "abc"}, "tree is not a commit id"),
        ({**document, "message": 7}, "malformed: message"),
        ({**document, "message": "Merge\n\nSignetum-Member: forged\n"}, "message is invalid"),
        ({**document, "member": 7}, "malformed: member"),
        ({**document, "parents": [source, before]}, "operation parents are invalid"),
        ({**document, "parents": [before, "abc"]}, "parent is not a commit id"),
        ({**document, "plans": "changes/contract/change.toml"}, "malformed: plans"),
        ({**document, "sync_kind": "sideways"}, "sync kind is invalid"),
        ({**document, "mappings": [["only-one"]]}, "mappings are invalid"),
        ({**document, "patch_id": 7}, "malformed: patch_id"),
        ({**document, "ready_evidence_sha256": "abc"}, "qualification identity is invalid"),
        ({**document, "continuation_messages": [7]}, "continuation messages are invalid"),
        ({**document, "status": "pending"}, "pending operation cannot carry proof"),
        ({**document, "proof": {"commit": before}}, "operation proof shape is invalid"),
        ({**document, "branch": "batch/elsewhere"}, "identity does not match its fields"),
    ]
    missing = dict(document)
    del missing["mappings"]
    cases.append((missing, "malformed: mappings"))
    for candidate, match in cases:
        with pytest.raises(AdmissionError, match=match):
            records.parse_operation(candidate)


def test_a_record_that_no_longer_matches_git_is_refused_where_used(admitted):
    batch, document, _ = admitted
    proof = dict(document["proof"])
    proof["tree"] = EMPTY_TREE
    with pytest.raises(AdmissionError, match="does not match the Git object"):
        records.require_bound_commit(batch, {**document, "proof": proof})
    with pytest.raises(AdmissionError, match="operation is not complete"):
        records.require_bound_commit(batch, {**document, "status": "pending", "proof": None})


def test_a_new_record_must_hold_its_kind_relations(admitted):
    batch, document, orphan = admitted
    before, source = document["before"], document["source"]
    before_tree = git_output(batch, "rev-parse", f"{before}^{{tree}}")
    pending = {**document, "status": "pending", "proof": None}
    loose = {**pending, "member": None, "ready_evidence": "", "ready_evidence_sha256": ""}
    single = {**loose, "parents": [before], "tree": before_tree}
    cases = [
        ({**pending, "base": orphan, "attested_base": orphan}, "not an ancestor of the merge"),
        ({**pending, "parents": [before, before], "source": before}, "not its second parent"),
        ({**pending, "member": None}, "admission record is invalid"),
        ({**loose, "kind": "member-sync"}, "member-sync record is invalid"),
        ({**loose, "kind": "batch-sync"}, "batch-sync record is invalid"),
        ({**pending, "kind": "publication"}, "publication record is invalid"),
        (
            {
                **loose,
                "kind": "publication",
                "base": before,
                "attested_base": before,
                "tree": before_tree,
            },
            "publication tree is not the published source tree",
        ),
        ({**single, "kind": "decision-mapping"}, "decision-mapping record is invalid"),
        (
            {**single, "kind": "decision-mapping", "base": orphan, "attested_base": orphan},
            "decision-mapping is not bound to its base",
        ),
        (
            {**single, "kind": "decision-mapping", "mappings": [["docs/a.md", "docs/b.md"]]},
            "decision mapping does not match the committed rename",
        ),
        ({**loose, "kind": "decision-mapping"}, "decision-mapping record is invalid"),
    ]
    assert source != before
    for candidate, match in cases:
        candidate = {**candidate, "id": records.intent_from_document(candidate).identity()}
        with pytest.raises(AdmissionError, match=match):
            records.validate_operation(batch, candidate)


def test_qualification_bytes_must_exist_for_an_admission(admitted):
    batch, document, _ = admitted
    digest = str(document["ready_evidence_sha256"])
    stored = records.state_root(batch) / "operations" / "qualifications" / digest
    content = stored.read_bytes()
    stored.unlink()
    try:
        with pytest.raises(AdmissionError, match="qualification bytes are missing"):
            records.validate_operation(batch, document)
        assert records.qualification_bytes(batch, "not-a-digest") is None
    finally:
        assert records.store_qualification(batch, content) == digest
    stored.write_bytes(b"tampered")
    with pytest.raises(AdmissionError, match="do not match their digest"):
        records.qualification_bytes(batch, digest)
    stored.write_bytes(content)
    assert records.validate_operation(batch, document) == document


def test_completion_and_continuation_refuse_what_was_not_recorded(admitted):
    batch, document, _ = admitted
    intent = records.intent_from_document(document)
    before = str(document["before"])
    with pytest.raises(AdmissionError, match="parents do not match the recorded intent"):
        records.complete_operation(batch, intent, before)
    elsewhere = records.intent_from_document({**document, "branch": "batch/elsewhere"})
    commit = str(document["proof"]["commit"])
    with pytest.raises(AdmissionError, match="completion has no pending intent"):
        records.complete_operation(batch, elsewhere, commit)
    assert records.complete_operation(batch, intent, commit)["proof"] == document["proof"]
    with pytest.raises(AdmissionError, match="continuation has no pending operation"):
        records.remember_continuation(batch, elsewhere, ("Later member.\n",))
    with pytest.raises(AdmissionError, match="continuation conflicts with the recorded operation"):
        records.remember_continuation(batch, intent, ("Later member.\n",))
    assert records.continuation_messages(batch, commit) is None
    assert records.continuation_messages(batch, before) is None


def test_stored_qualification_bytes_cannot_be_replaced(admitted):
    batch, document, _ = admitted
    digest = str(document["ready_evidence_sha256"])
    stored = records.state_root(batch) / "operations" / "qualifications" / digest
    content = stored.read_bytes()
    assert records.store_qualification(batch, content) == digest
    stored.write_bytes(b"replaced")
    try:
        with pytest.raises(AdmissionError, match="conflict with the recorded digest"):
            records.store_qualification(batch, content)
    finally:
        stored.write_bytes(content)


def test_decision_mapping_requires_a_real_numbering_commit(admitted):
    batch, document, orphan = admitted
    merge = str(document["proof"]["commit"])
    before = str(document["before"])
    message = records.commit_message(batch, merge)
    with pytest.raises(AdmissionError, match="cannot carry Signetum trailers"):
        records.record_decision_mapping(
            batch, merge, before, "docs/decisions", "Number\n\nSignetum-Base: x\n"
        )
    with pytest.raises(AdmissionError, match="decision mapping commit is unavailable"):
        records.record_decision_mapping(batch, "no-such-commit", before, "docs", "Number\n")
    with pytest.raises(AdmissionError, match="message does not match the commit"):
        records.record_decision_mapping(batch, merge, before, "docs", "Another message\n")
    with pytest.raises(AdmissionError, match="must have one parent"):
        records.record_decision_mapping(batch, merge, before, "docs", message)
    source = str(document["source"])
    with pytest.raises(AdmissionError, match="not bound to the approved base"):
        records.record_decision_mapping(
            batch, source, orphan, "docs", records.commit_message(batch, source)
        )
    with pytest.raises(AdmissionError, match="does not match the committed rename"):
        records.record_decision_mapping(
            batch, source, before, "docs/decisions", records.commit_message(batch, source)
        )


def test_stored_files_that_do_not_parse_or_repeat_an_identity_are_refused(admitted):
    batch, document, _ = admitted
    directory = records.state_root(batch) / "operations" / "records"
    stored = directory / f"{document['id']}.json"
    garbage = directory / "garbage.json"
    garbage.write_text("{not json", encoding="utf-8")
    with pytest.raises(AdmissionError, match=r"operation record is unreadable: garbage\.json"):
        records.load_index(batch)
    garbage.unlink()
    copy = directory / "copy.json"
    copy.write_bytes(stored.read_bytes())
    with pytest.raises(AdmissionError, match="identity is recorded twice"):
        records.load_index(batch)
    copy.unlink()
    assert records.load_index(batch).for_commit(str(document["proof"]["commit"])) == document


def test_beginning_a_completed_operation_again_returns_its_proof(admitted):
    batch, document, _ = admitted
    intent = records.intent_from_document(document)
    assert records.begin_operation(batch, intent) == document
    other = records.intent_from_document({**document, "message": "Another description.\n"})
    assert records.begin_operation(batch, other) == document


def test_batch_history_names_only_recorded_admissions(admitted):
    batch, document, orphan = admitted
    base, tip = str(document["attested_base"]), str(document["proof"]["commit"])
    members, _ = members_and_plans(batch, base, tip)
    assert [item["original"] for item in members] == [document["source"]]
    with pytest.raises(AdmissionError, match="unrecognized merge authority"):
        members_and_plans(batch, orphan, tip)
    with pytest.raises(AdmissionError, match="no admitted member provenance"):
        members_and_plans(batch, tip, tip)
    side = git_output(batch, "commit-tree", EMPTY_TREE, "-p", base, "-m", "side")
    manual = git_output(batch, "commit-tree", EMPTY_TREE, "-p", tip, "-p", side, "-m", "manual")
    with pytest.raises(AdmissionError, match="unrecorded merge"):
        members_and_plans(batch, base, manual)
