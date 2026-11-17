"""Message intake and retained old-engine text around operation records."""

from pathlib import Path

import pytest
from signetum import operation_records as records
from signetum.operations import AdmissionError

OID = "a" * 40
OTHER = "b" * 40


def test_caller_messages_are_frozen_before_any_git_effect(tmp_path):
    assert records.freeze_message("subject") == "subject\n"
    for text, match in (("kept\0hidden", "contains NUL"), ("  \n", "is empty")):
        with pytest.raises(AdmissionError, match=match):
            records.freeze_message(text)
    cases = {
        "nul.txt": (b"kept\0hidden\n", "contains NUL"),
        "binary.txt": (b"\xff\n", "is not UTF-8"),
        "blank.txt": (b" \n", "is empty"),
    }
    for name, (content, match) in cases.items():
        (tmp_path / name).write_bytes(content)
        with pytest.raises(AdmissionError, match=match):
            records.read_message_file(tmp_path / name)
    with pytest.raises(AdmissionError, match=r"message file is missing: absent\.txt"):
        records.read_message_file(tmp_path / "absent.txt")
    with pytest.raises(AdmissionError, match="a message file is required"):
        records.read_message_files(())
    (tmp_path / "ok.txt").write_text("Merge work\n", encoding="utf-8")
    assert records.read_message_files((tmp_path / "ok.txt",)) == ("Merge work\n",)


@pytest.mark.parametrize(
    ("message", "proof"),
    [
        (f"Merge delivery into change/a\n\nSignetum-Sync: {OID}\nSignetum-Sync-Source: x\n", True),
        (f"Merge delivery into change/a\n\nSignetum-Sync: {OID}\n", False),
        ("Merge delivery into change/a\n\nSignetum-Sync: short\nSignetum-Sync-Source: x\n", False),
        (
            "Merge delivered history into batch/a\n\n"
            f"Signetum-Batch-Sync: {OID}\nSignetum-Batch-Base: {OID}\n"
            f"Signetum-Previous-Batch-Base: {OTHER}\n",
            True,
        ),
        (
            f"Merge task into main\n\nSignetum-Batch-Base: {OID}\nSignetum-Batch-Tip: {OTHER}\n",
            True,
        ),
        (
            "Merge change/a into integration batch\n\n"
            f"Signetum-Base: {OID}\nSignetum-Original: {OTHER}\nSignetum-Member: change/a\n"
            f"Signetum-Batch-Base: {OID}\nSignetum-Patch-ID: {OID}\n"
            "Signetum-Ready-Evidence: member-lifecycle.json\n",
            True,
        ),
        (
            "Merge change/a into integration batch\n\n"
            f"Signetum-Base: {OID}\nSignetum-Member: change/a\n",
            False,
        ),
        (f"Merge task into main\n\nSignetum-Forged: {OID}\nSignetum-Batch-Base: {OID}\n", False),
        (f"Manual merge\n\n Signetum-Sync: {OID}\nSignetum-Sync-Source: x\n", False),
    ],
)
def test_only_exact_old_engine_text_is_legacy_proof(message, proof):
    assert records.legacy_proof_message(message) is proof


def test_record_readers_refuse_incomplete_facts(tmp_path):
    assert records.batch_sync_record({"kind": "admission"}) is None
    with pytest.raises(AdmissionError, match="batch synchronization record is incomplete"):
        records.batch_sync_record({"kind": "batch-sync", "source": OID})
    assert records.batch_sync_record(
        {"kind": "batch-sync", "source": OID, "previous_base": OTHER}
    ) == (OTHER, OID)
    with pytest.raises(AdmissionError, match="admission record is missing its member"):
        records.member_from_record({"source": OID, "member": ""}, OID, "summary")
    with pytest.raises(AdmissionError, match="ready evidence path is invalid"):
        records.evidence_sha256(Path(tmp_path), tmp_path, "../escape.json")
    with pytest.raises(AdmissionError, match="ready evidence path is invalid"):
        records.evidence_sha256(Path(tmp_path), tmp_path, "absent.json")
    with pytest.raises(AdmissionError, match="operation kind is invalid"):
        records.OperationIntent("rebase", "b", OID, OTHER, OID, "m\n", OID, (OID,))
    with pytest.raises(AdmissionError, match="parents do not start at its before commit"):
        records.OperationIntent("admission", "b", OID, OTHER, OID, "m\n", OID, (OTHER,))
