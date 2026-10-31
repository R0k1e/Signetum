"""A workspace record is the single authority for the base it was cut from."""

import json
from pathlib import Path

import pytest
from signetum.workspaces import (
    WorkspaceError,
    WorkspaceRecord,
    claim_change,
    parse_record,
    read_record,
    record_path,
    write_record,
)

BASE = "a" * 40
OTHER = "b" * 40


def _record(**overrides: object) -> WorkspaceRecord:
    values: dict[str, object] = {
        "schema_version": 1,
        "branch": "plan/example",
        "base": BASE,
        "kind": "member",
    }
    values.update(overrides)
    return parse_record(values)


def test_a_branch_name_survives_the_round_trip_through_its_path(tmp_path: Path) -> None:
    record = _record(branch="feat/a b/c")

    write_record(tmp_path, record)

    assert read_record(tmp_path, "feat/a b/c") == record
    assert "/" not in record_path(tmp_path, "feat/a b/c").name


def test_a_batch_records_the_members_it_declares(tmp_path: Path) -> None:
    record = _record(kind="batch", members=("/w/one", "/w/two"))

    write_record(tmp_path, record)

    assert read_record(tmp_path, "plan/example").members == ("/w/one", "/w/two")


def test_repeating_the_same_identity_is_idempotent(tmp_path: Path) -> None:
    write_record(tmp_path, _record())

    original = record_path(tmp_path, "plan/example").read_bytes()
    write_record(tmp_path, _record())
    assert record_path(tmp_path, "plan/example").read_bytes() == original
    with pytest.raises(WorkspaceError, match="different recorded identity"):
        write_record(tmp_path, _record(kind="batch"))


def test_a_recorded_base_cannot_be_replaced(tmp_path: Path) -> None:
    write_record(tmp_path, _record())

    with pytest.raises(WorkspaceError, match="already recorded at base"):
        write_record(tmp_path, _record(base=OTHER))


def test_a_missing_record_names_the_path_and_the_adoption_shape(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError) as failure:
        read_record(tmp_path, "plan/absent")

    message = str(failure.value)
    assert str(record_path(tmp_path, "plan/absent")) in message
    assert "schema_version" in message


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        pytest.param("{not json", "unreadable", id="unparsable"),
        pytest.param(
            json.dumps({"schema_version": 2, "branch": "b", "base": BASE, "kind": "member"}),
            "unsupported workspace record schema",
            id="wrong-version",
        ),
        pytest.param(
            json.dumps({"schema_version": 1, "branch": "b", "base": "head", "kind": "member"}),
            "exact commit identity",
            id="inexact-base",
        ),
        pytest.param(
            json.dumps({"schema_version": 1, "branch": "b", "base": BASE, "kind": "trunk"}),
            "invalid",
            id="unsupported-kind",
        ),
        pytest.param(
            json.dumps(
                {
                    "schema_version": 1,
                    "branch": "b",
                    "base": BASE,
                    "kind": "batch",
                    "members": ["/w", "/w"],
                }
            ),
            "unique",
            id="duplicate-members",
        ),
    ],
)
def test_an_unusable_record_fails_closed(tmp_path: Path, document: str, expected: str) -> None:
    path = record_path(tmp_path, "plan/example")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")

    with pytest.raises(WorkspaceError, match=expected):
        read_record(tmp_path, "plan/example")


def test_a_change_owner_can_retry_but_cannot_fork_its_implementation(tmp_path):
    claim_change(tmp_path, "example", "plan/example")
    claim_change(tmp_path, "example", "plan/example")
    with pytest.raises(WorkspaceError, match="already belongs to member plan/example"):
        claim_change(tmp_path, "example", "impl/example")


@pytest.mark.parametrize(
    "document",
    [
        {"change_id": "example", "member": "plan/example"},
        {"schema_version": True, "change_id": "example", "member": "plan/example"},
        {"schema_version": 1, "change_id": "../example", "member": "plan/example"},
        {"schema_version": 1, "change_id": "example", "member": ""},
        {"schema_version": 1, "change_id": "example", "member": "plan/example", "extra": "unknown"},
    ],
)
def test_invalid_owner_is_preserved_and_cannot_be_silently_adopted(tmp_path, document):
    path = tmp_path / "changes/example/owner.json"
    path.parent.mkdir(parents=True)
    original = json.dumps(document)
    path.write_text(original)
    with pytest.raises(WorkspaceError, match="unreadable"):
        claim_change(tmp_path, "example", "plan/example")
    assert path.read_text() == original


@pytest.mark.parametrize("members", [["/one"], ("",), (1,)])
def test_constructed_record_requires_immutable_string_members(members):
    with pytest.raises(WorkspaceError, match="non-empty strings"):
        WorkspaceRecord(
            schema_version=1, branch="plan/example", base=BASE, kind="batch", members=members
        )
