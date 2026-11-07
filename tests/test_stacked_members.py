"""Real Git scenarios for a chain of stacked members delivered through one batch."""

import json
from pathlib import Path
from typing import Any

import pytest
from change_fixtures import commit_approval
from signetum import lifecycle, maintenance
from signetum import workspace_operations as ops
from signetum.development_store import snapshot
from signetum.git import git_output
from signetum.operations import AdmissionError
from signetum.workflow_status import workflow_status
from signetum.workspaces import read_record, state_root, workspace_destination

PARENT = "change/parent"
CHILD = "change/child"


def opened(root, branch, base):
    result = ops.workspace_open(root, branch, base)
    return Path(str(result["worktree"])), result


def commit_file(repository, name, value="work"):
    (repository / name).write_text(value)
    git_output(repository, "add", name)
    git_output(repository, "commit", "-m", f"implement {name}")


def tip(repository):
    return git_output(repository, "rev-parse", "HEAD")


def chain(root):
    """A ready parent member and a ready child stacked on its tip."""
    parent, _ = opened(root, PARENT, "main")
    commit_approval(parent, "parent")
    commit_file(parent, "parent.txt")
    lifecycle.validate(parent, "member")
    child, result = opened(root, CHILD, PARENT)
    commit_approval(child, "child")
    commit_file(child, "child.txt")
    return parent, child, result


def contribution(receipt):
    details = receipt["evidence"]["extensions"]["shard_details"]["test:check"]
    return json.loads(details["environment"]["SIGNETUM_CONTRIBUTION_PATHS"])


def sync_parent(member, monkeypatch, capsys):
    monkeypatch.chdir(member)
    capsys.readouterr()
    code = maintenance.main(["workspace-sync"])
    return code, json.loads(capsys.readouterr().out)


def view(repository):
    return workflow_status(repository, snapshot(repository), source=tip(repository))


def test_member_opened_on_a_member_qualifies_only_its_own_diff(repository):
    root, _ = repository
    parent, child, result = chain(root)
    parent_tip = git_output(parent, "rev-parse", "HEAD")

    record = read_record(state_root(root), CHILD)
    assert (record.parent, record.base) == (PARENT, parent_tip)
    assert result["parent"] == PARENT and result["base"] == parent_tip
    assert read_record(state_root(root), PARENT).parent is None

    ready: Any = lifecycle.validate(child, "member")

    assert ready["base"] == parent_tip
    assert contribution(ready) == ["changes/child/change.toml", "child.txt"]
    assert [item["change_id"] for item in ready["approvals"]] == ["child"]


def test_parent_change_requires_sync_down_before_ready(repository, monkeypatch, capsys):
    root, _ = repository
    parent, child, _ = chain(root)
    lifecycle.validate(child, "member")
    held = read_record(state_root(root), CHILD).base
    commit_file(parent, "parent-fix.txt")

    assert "workspace-sync" in view(child)["next"]
    with pytest.raises(AdmissionError, match=PARENT) as refusal:
        lifecycle.validate(child, "member")
    assert "workspace-sync" in refusal.value.expected
    reopened, resumed = opened(root, CHILD, PARENT)
    assert reopened == child and resumed["resumed"] and resumed["base"] == held

    code, synced = sync_parent(child, monkeypatch, capsys)

    assert code == 0, synced
    assert synced["outcome"] == "synchronized" and synced["source"] == tip(parent)
    assert "workspace-sync" not in view(child)["next"]
    ready = lifecycle.validate(child, "member")
    following = view(child)["next"]
    assert following.index(PARENT) < following.index(CHILD)
    assert (child / "parent-fix.txt").exists()
    assert contribution(ready) == ["changes/child/change.toml", "child.txt"]
    code, repeated = sync_parent(child, monkeypatch, capsys)
    assert code == 0 and repeated["outcome"] == "unchanged"


def test_admission_requires_the_parent_first_at_the_held_tip(repository):
    root, _ = repository
    parent, child, _ = chain(root)
    lifecycle.validate(child, "member")
    batch = workspace_destination(root, "batch/chain")
    base = tip(root)

    with pytest.raises(AdmissionError, match="admit the chain in order") as refusal:
        lifecycle.batch_open(root, (child, parent), name="chain")
    assert tip(batch) == base
    assert refusal.value.expected.index(str(parent)) < refusal.value.expected.index(str(child))

    result: Any = lifecycle.admit(batch, (parent, child))

    assert [item["branch"] for item in result["admitted"]] == [PARENT, CHILD]
    assert result["admission_base"] == base


def test_final_review_names_the_chain_and_delivery_removes_it(repository):
    root, _ = repository
    parent, child, _ = chain(root)
    lifecycle.validate(child, "member")
    parent_tip, child_tip = tip(parent), tip(child)
    batch = Path(str(lifecycle.batch_open(root, (parent, child), name="chain")["worktree"]))

    final: Any = lifecycle.validate(batch, "final")

    review = final["delivery_review"]["inputs"]["member_chain"]
    assert [(item["member"], item["changes"], item["parent"]) for item in review] == [
        (PARENT, ["parent"], None),
        (CHILD, ["child"], PARENT),
    ]
    assert review[1]["parent_tip"] == parent_tip
    delivered: Any = lifecycle.batch_deliver(
        batch, root, lifecycle._recorded_base(batch), str(final["source"])
    )
    removed = {item["branch"]: item for item in delivered["removed_worktrees"]}
    assert removed[PARENT]["tip"] == parent_tip and removed[CHILD]["tip"] == child_tip
    assert {removed[PARENT]["outcome"], removed[CHILD]["outcome"]} == {"delivered"}
