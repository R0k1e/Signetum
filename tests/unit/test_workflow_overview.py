"""The current overview follows real workspace, journal and evidence authorities."""

from dataclasses import replace
from pathlib import Path

from change_fixtures import consolidated_approval

from signetum import lifecycle
from signetum.change_record import contract_digest, parse_change_record
from signetum.development_store import append_transaction, parse_request, snapshot
from signetum.git import git_output, run_git
from signetum.workflow_status import workflow_status
from signetum.workspaces import WorkspaceRecord, state_root, write_record


def _view(root):
    return workflow_status(root, snapshot(root), source=git_output(root, "rev-parse", "HEAD"))


def _commit(root, message):
    git_output(root, "add", ".")
    git_output(root, "commit", "--allow-empty", "-m", message)


def test_overview_is_read_only_scoped_and_distinguishes_recorded_readiness(local_repository):
    root, _ = local_repository
    common = (
        Path(git_output(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        / "signetum"
    )
    existed = common.exists()
    before = git_output(root, "status", "--porcelain")
    assert _view(root)["workspace"] is None
    assert common.exists() == existed and git_output(root, "status", "--porcelain") == before
    base = git_output(root, "rev-parse", "HEAD")
    branch = "plan/overview"
    git_output(root, "switch", "-c", branch)
    write_record(state_root(root), WorkspaceRecord(1, branch, base, "member"))
    assert _view(root)["changes"] == []
    consolidated_approval(root, base, approved=False)
    _commit(root, "draft outcome")
    assert _view(root)["changes"][0]["approved"] is False
    consolidated_approval(root, base)
    _commit(root, "approve outcome")
    (root / "seed.txt").write_text("implemented")
    _commit(root, "implement outcome")
    record = parse_change_record((root / "changes/example/change.toml").read_text())
    request = {
        "id": "example/finding",
        "change_id": "example",
        "approval_digest": contract_digest(record.contract),
        "operation": "record",
        "reason": "Retain a significant finding.",
        "observations": [
            {
                "id": "example/observed",
                "requirements": ["REQ-1"],
                "summary": "An owned finding.",
                "reason": "Its verified basis.",
            }
        ],
    }
    state = append_transaction(
        root, parse_request(request), expected_history=snapshot(root).history_digest
    )
    _commit(root, "retain finding")
    actual = snapshot(root)
    other = replace(actual.observations[0], change_id="another-change")
    scoped = workflow_status(
        root,
        replace(actual, observations=(*actual.observations, other)),
        source=git_output(root, "rev-parse", "HEAD"),
    )
    observations = scoped["observations"]
    assert isinstance(observations, list) and len(observations) == 1
    assert scoped["pending"] == ["example/observed"]
    request = {
        **request,
        "id": "example/answer",
        "operation": "resolve",
        "observations": [],
        "resolutions": [
            {
                "id": "example/resolved",
                "target": "example/observed",
                "status": "rejected",
                "reason": "Existing behavior already satisfies it.",
            }
        ],
    }
    append_transaction(root, parse_request(request), expected_history=state.history_digest)
    _commit(root, "retain disposition")
    assert _view(root)["pending"] == []
    lifecycle.validate(root, "member")
    assert _view(root)["receipts"][0]["source_current"] is True
    (root / "user-work").touch()
    assert _view(root)["dirty"] and _view(root)["receipts"][0]["source_current"] is False
    (root / "user-work").unlink()
    _commit(root, "advance source")
    (common / "validation/member-lifecycle-damaged.json").write_text("not JSON")
    assert _view(root)["receipts"] == []
    git_output(root, "switch", "-c", "batch/overview")
    write_record(state_root(root), WorkspaceRecord(1, "batch/overview", base, "batch", (branch,)))
    view = _view(root)
    assert view["workspace"]["kind"] == "batch" and view["changes"][0]["id"] == "example"
    git_output(root, "switch", "-c", "incoming")
    (root / "seed.txt").write_text("left")
    _commit(root, "left change")
    git_output(root, "switch", "batch/overview")
    (root / "seed.txt").write_text("right")
    _commit(root, "right change")
    assert run_git(root, "merge", "incoming").returncode == 1
    assert _view(root)["merge_open"] is True
