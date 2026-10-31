"""Installed candidate previews expose current context without creating authority."""

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from signetum.decision_clauses import ClauseRevision, DecisionEdit, ExpectedClause
from signetum.decision_history import (
    DecisionTransaction,
    TopicEdit,
    TopicRevision,
    TransactionProposal,
    project_decision_history,
)
from signetum.serialization import contract_mapping


@pytest.fixture
def proposal():
    clause = ClauseRevision(
        id="VAL-001",
        version=1,
        topic="validation",
        scope=("repository",),
        statement="Retain the first failure.",
        rationale="A retry is diagnostic.",
    )
    edit = DecisionEdit(
        id="example/rule",
        change_id="example",
        action="add",
        expected=(ExpectedClause(id=clause.id, version=0),),
        updates=(clause,),
        reason="Explicit candidate rule.",
        authority="example/contract",
    )
    event = DecisionTransaction(
        id="example/transaction",
        change_id="example",
        authority="example/contract",
        reason="Candidate context.",
        clauses=(edit,),
        topics=(
            TopicEdit(
                expected_version=0,
                revision=TopicRevision(
                    id="validation",
                    version=1,
                    summary="Validate the actual workload before delivery.",
                    boundaries=("A preview grants no authority.",),
                ),
            ),
        ),
    )
    return TransactionProposal(schema_version=1, transaction=event)


@pytest.mark.parametrize("frontend", ["engine"])
@pytest.mark.parametrize("valid", [True, False])
def test_candidate_history_preview_is_read_only_and_rejects_missing_predecessors(
    tmp_path,
    proposal,
    frontend,
    valid,
):
    if not valid:
        proposal = replace(proposal, transaction=replace(proposal.transaction, parents=("absent",)))
    candidate = tmp_path / "candidate.jsonl"
    candidate.write_text(json.dumps(contract_mapping(proposal)) + "\n")
    before = candidate.read_bytes()
    runtime = Path(__file__).parents[2] / "tests/fixtures/portable-python/.agents/signetum/runtime"
    script = """
import sys
sys.path.insert(0,sys.argv[1])
from signetum.decision_history import main
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules
raise SystemExit(main([sys.argv[2]]))
"""
    argv = (
        ["-m", "signetum.decision_history", str(candidate)]
        if frontend == "engine"
        else ["-I", "-S", "-c", script, str(runtime), str(candidate)]
    )
    result = subprocess.run(  # noqa: S603 -- isolated preview, explicit disposable candidate input
        [sys.executable, *argv],
        capture_output=True,
        text=True,
        check=False,
    )
    if valid:
        assert result.returncode == 0, result.stderr
        preview = json.loads(result.stdout)
        assert preview["status"] == "preview"
        assert preview["working_set"]["topics"][0]["revision"]["summary"] == (
            proposal.transaction.topics[0].revision.summary
        )
        assert preview["working_set"]["clauses"][0]["source_event"] == "example/rule"
    else:
        assert result.returncode == 2
        assert not result.stdout
        assert json.loads(result.stderr)["status"] == "invalid"
    assert candidate.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["candidate.jsonl"]


@pytest.mark.parametrize("damage", [False, True])
def test_a_projection_cannot_be_edited_independently_of_its_history(tmp_path, proposal, damage):
    candidate = tmp_path / "candidate.jsonl"
    candidate.write_text(json.dumps(contract_mapping(proposal)) + "\n")
    projection = tmp_path / "current.json"
    value = json.loads(
        json.dumps(contract_mapping(project_decision_history((proposal.transaction,))))
    )
    if damage:
        value["clauses"][0]["revision"]["statement"] = "An unrecorded replacement rule."
    projection.write_text(json.dumps(value))
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    result = subprocess.run(  # noqa: S603 -- real read-only preview and explicit fixture files
        [
            sys.executable,
            "-m",
            "signetum.decision_history",
            str(candidate),
            "--check-projection",
            str(projection),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (2 if damage else 0), result.stdout + result.stderr
    if damage:
        assert "differs from its decision history" in json.loads(result.stderr)["reason"]
    else:
        assert json.loads(result.stdout)["projection_checked"] is True
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
