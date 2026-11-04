"""Real Git scenarios for an open batch after a sibling batch delivers."""

import json
from pathlib import Path

import pytest
from change_fixtures import commit_approval
from signetum import change_cli, lifecycle, maintenance
from signetum import workspace_operations as ops
from signetum.change_record import contract_digest, parse_change_record
from signetum.git import git_output, run_git
from signetum.operations import AdmissionError, MergeConflict
from signetum.provenance import members_and_plans


def opened(repository, branch):
    result = ops.workspace_open(repository, branch, git_output(repository, "rev-parse", "HEAD"))
    return Path(str(result["worktree"]))


def commit_file(repository, name, value="work"):
    (repository / name).write_text(value)
    git_output(repository, "add", name)
    git_output(repository, "commit", "-m", f"implement {name}")


def ready_member(root, change_id, name, value="work", *, clause=None):
    member = opened(root, f"change/{change_id}")
    if clause is None:
        commit_approval(member, change_id)
    else:
        claim_clause(member, change_id, clause)
    commit_file(member, name, value)
    lifecycle.validate(member, "member")
    return member


def claim_clause(member, change_id, clause):
    base = lifecycle._recorded_base(member)
    authority = f"changes/{change_id}/change.toml#decisions/{change_id}/rule"
    text = f'''[change]
schema_version = 1
id = "{change_id}"
[change.source]
kind = "human_direction"
summary = "Implement the confirmed outcome."
[change.contract]
version = 1
approved_base = "{base}" # pragma: allowlist secret
[[change.contract.requirements]]
id = "REQ-1"
outcome = "Implement the confirmed behavior."
acceptance = ["The declared member check passes."]
[[change.contract.decisions]]
id = "{change_id}/rule"
change_id = "{change_id}"
authority = "{authority}"
reason = "Record the rule."
[[change.contract.decisions.topics]]
expected_version = 0
[change.contract.decisions.topics.revision]
id = "{change_id}-topic"
version = 1
summary = "Fixture rules."
[[change.contract.decisions.clauses]]
id = "{change_id}/add-rule"
change_id = "{change_id}"
action = "add"
expected = [{{ id = "{clause}", version = 0 }}]
reason = "Add the rule."
authority = "{authority}"
[[change.contract.decisions.clauses.updates]]
id = "{clause}"
version = 1
topic = "{change_id}-topic"
scope = ["Fixture"]
statement = "The {change_id} rule."
rationale = "Fixture."
[[change.execution.steps]]
id = "STEP-1"
requirements = ["REQ-1"]
action = "Implement and validate the outcome."
'''
    digest = contract_digest(parse_change_record(text).contract)
    text += f'''[change.approval]
actor = "Owner"
recorded_at = 2026-11-04
source = "Owner confirmed the fixture outcome."
contract_digest = "{digest}"
'''
    path = member / f"changes/{change_id}/change.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", f"approve change {change_id}")
    accepted = change_cli.main(
        [
            "reconcile",
            "--id",
            "accept",
            "--reason",
            "Apply the approved rule.",
            "--accept-decisions",
            "--repository",
            str(member),
        ]
    )
    assert accepted == 0
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", f"accept the {change_id} rule")


def open_batch(root, member):
    return Path(str(lifecycle.batch_open(root, (member,))["worktree"]))


def deliver(root, batch):
    base = lifecycle._recorded_base(batch)
    tip = lifecycle.validate(batch, "final")["source"]
    assert isinstance(tip, str)
    return lifecycle.batch_deliver(batch, root, base, tip)


def synchronize(batch, monkeypatch, capsys, *arguments):
    monkeypatch.chdir(batch)
    capsys.readouterr()
    code = maintenance.main(["workspace-sync", *arguments])
    result = json.loads(capsys.readouterr().out)
    return code, result


def parallel_batches(root, *, first=("first.txt", "first"), second=("second.txt", "second")):
    batch_a = open_batch(root, ready_member(root, "first", *first))
    batch_b = open_batch(root, ready_member(root, "second", *second))
    return batch_a, batch_b


def test_open_batch_takes_a_sibling_delivery_and_delivers(repository, monkeypatch, capsys):
    root, _ = repository
    original = git_output(root, "rev-parse", "HEAD")
    batch_a, batch_b = parallel_batches(root)
    admitted, _ = members_and_plans(batch_b, original, git_output(batch_b, "rev-parse", "HEAD"))
    deliver(root, batch_a)
    delivered = git_output(root, "rev-parse", "HEAD")
    stale = lifecycle.validate(batch_b, "final")["source"]
    assert isinstance(stale, str)
    with pytest.raises(AdmissionError, match="remote delivery branch differs") as refusal:
        lifecycle.batch_deliver(batch_b, root, original, stale)
    assert "workspace-sync" in refusal.value.expected

    code, result = synchronize(batch_b, monkeypatch, capsys)

    assert code == 0, result
    assert result["outcome"] == "synchronized"
    assert result["admission_base"] == stale
    assert result["previous_base"] == original
    assert lifecycle._recorded_base(batch_b) == delivered
    tip = git_output(batch_b, "rev-parse", "HEAD")
    assert git_output(batch_b, "show", "-s", "--format=%P", tip).split()[1] == delivered
    assert (batch_b / "first.txt").read_text() == "first"
    members, _ = members_and_plans(batch_b, delivered, tip)
    assert members == admitted
    code, repeated = synchronize(batch_b, monkeypatch, capsys)
    assert code == 0 and repeated["outcome"] == "unchanged"

    final = lifecycle.validate(batch_b, "final")
    assert final["base"] == delivered
    with pytest.raises(AdmissionError, match="recorded batch base differs"):
        lifecycle.batch_deliver(batch_b, root, original, tip)
    result = lifecycle.batch_deliver(batch_b, root, delivered, tip)
    assert result["members"] == admitted
    assert git_output(root, "show", "-s", "--format=%P", "HEAD").split() == [delivered, tip]
    assert {(root / "first.txt").read_text(), (root / "second.txt").read_text()} == {
        "first",
        "second",
    }


def test_conflicting_sibling_delivery_completes_through_batch_continue(
    repository, monkeypatch, capsys
):
    root, _ = repository
    original = git_output(root, "rev-parse", "HEAD")
    batch_a, batch_b = parallel_batches(
        root, first=("shared.txt", "first"), second=("shared.txt", "second")
    )
    deliver(root, batch_a)
    delivered = git_output(root, "rev-parse", "HEAD")

    code, refusal = synchronize(batch_b, monkeypatch, capsys)

    assert code != 0
    assert refusal["status"] == "conflict", refusal
    assert "batch-continue" in refusal["expected"]
    assert lifecycle._recorded_base(batch_b) == original
    with pytest.raises(MergeConflict, match="open merge"):
        lifecycle.validate(batch_b, "final")
    (batch_b / "shared.txt").write_text("first and second")
    git_output(batch_b, "add", "shared.txt")
    continued = lifecycle.continue_batch(batch_b)
    tip = git_output(batch_b, "rev-parse", "HEAD")
    assert continued["batch_commit"] == tip
    assert lifecycle._recorded_base(batch_b) == delivered
    assert lifecycle.validate(batch_b, "final")["source"] == tip
    lifecycle.batch_deliver(batch_b, root, delivered, tip)
    assert (root / "shared.txt").read_text() == "first and second"


def test_batch_refuses_a_delivery_that_does_not_descend_from_its_base(
    repository, monkeypatch, capsys
):
    root, _ = repository
    original = git_output(root, "rev-parse", "HEAD")
    batch = open_batch(root, ready_member(root, "second", "second.txt"))
    before = git_output(batch, "rev-parse", "HEAD")
    git_output(root, "checkout", "--orphan", "rewritten")
    git_output(root, "commit", "-m", "rewritten delivery")
    git_output(root, "push", "--force", "origin", "rewritten:main")

    code, refusal = synchronize(batch, monkeypatch, capsys)

    assert code != 0 and "does not descend" in refusal["cause"], refusal
    _, named = synchronize(batch, monkeypatch, capsys, "--batch", str(batch))
    assert "only from the delivery branch" in named["cause"], named
    assert git_output(batch, "rev-parse", "HEAD") == before
    assert lifecycle._recorded_base(batch) == original


def test_admission_refuses_a_clause_identity_another_change_claims(repository):
    root, _ = repository
    first = ready_member(root, "first", "first.txt", clause="TOOL-OBJECT-005")
    second = ready_member(root, "second", "second.txt", clause="TOOL-OBJECT-005")
    batch = open_batch(root, first)
    before = git_output(batch, "rev-parse", "HEAD")
    with pytest.raises(AdmissionError) as refusal:
        lifecycle.admit(batch, (second,))
    message = str(refusal.value)
    assert "TOOL-OBJECT-005" in message
    assert "workspace change/first" in message and "workspace change/second" in message
    assert git_output(batch, "rev-parse", "HEAD") == before
    assert run_git(batch, "rev-parse", "--verify", "MERGE_HEAD").returncode != 0
    commit_file(first, "more.txt")
    lifecycle.validate(first, "member")
    assert lifecycle.admit(batch, (first,))["admitted"]


def test_sync_refuses_a_clause_identity_the_delivered_sibling_claims(
    repository, monkeypatch, capsys
):
    root, _ = repository
    batch_a = open_batch(root, ready_member(root, "first", "first.txt", clause="RULE-001"))
    batch_b = open_batch(root, ready_member(root, "second", "second.txt", clause="RULE-001"))
    before = git_output(batch_b, "rev-parse", "HEAD")
    deliver(root, batch_a)

    code, refusal = synchronize(batch_b, monkeypatch, capsys)

    assert code != 0
    assert "RULE-001" in refusal["cause"]
    assert "workspace change/first" in refusal["cause"]
    assert "workspace change/second" in refusal["cause"]
    assert git_output(batch_b, "rev-parse", "HEAD") == before


def test_batch_records_a_delivery_tip_a_member_already_merged(repository, monkeypatch, capsys):
    root, _ = repository
    batch_a = open_batch(root, ready_member(root, "first", "first.txt"))
    second = ready_member(root, "second", "second.txt")
    batch_b = open_batch(root, second)
    deliver(root, batch_a)
    delivered = git_output(root, "rev-parse", "HEAD")
    ops.workspace_sync(second)
    lifecycle.validate(second, "member")
    lifecycle.admit(batch_b, (second,))
    before = git_output(batch_b, "rev-parse", "HEAD")

    code, result = synchronize(batch_b, monkeypatch, capsys)

    assert code == 0 and result["outcome"] == "synchronized", result
    tip = git_output(batch_b, "rev-parse", "HEAD")
    assert git_output(batch_b, "show", "-s", "--format=%P", tip).split() == [before, delivered]
    assert git_output(batch_b, "rev-parse", f"{tip}^{{tree}}") == git_output(
        batch_b, "rev-parse", f"{before}^{{tree}}"
    )
    assert lifecycle.validate(batch_b, "final")["base"] == delivered
    lifecycle.batch_deliver(batch_b, root, delivered, tip)
