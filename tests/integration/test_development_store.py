"""Real Git authorization and atomic development-journal behavior."""

import fcntl
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum.change_record import contract_digest, parse_change_record
from signetum.git import git_output, run_git
from signetum.serialization import contract_mapping
from signetum.source_authority import authority_roots
from signetum.workspaces import WorkspaceRecord, write_record


@pytest.fixture
def store(request, monkeypatch):
    if getattr(request, "param", "engine") == "engine":
        return importlib.import_module("signetum.development_store")
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[2] / "template/.agents/repo-dev/runtime")
    )
    return importlib.import_module("_signetum_runtime.development_store")


@pytest.fixture
def repository(tmp_path):
    for arguments in (
        ("init", "-b", "main"),
        ("config", "user.name", "Journal test"),
        ("config", "user.email", "journal@example.invalid"),
    ):
        assert run_git(tmp_path, *arguments).returncode == 0
    (tmp_path / "behavior.py").write_text("assert True\n")
    git_output(tmp_path, "add", ".")
    git_output(tmp_path, "commit", "-m", "base")
    base = git_output(tmp_path, "rev-parse", "HEAD")
    git_output(tmp_path, "switch", "-c", "plan/alpha")
    common = Path(git_output(tmp_path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    write_record(common / "signetum", WorkspaceRecord(1, "plan/alpha", base, "member"))
    source = f'''[change]
schema_version = 1
id = "alpha"
[change.source]
kind = "human_direction"
summary = "Preserve the approved outcome."
[change.contract]
version = 1
approved_base = "{base}"
[[change.contract.requirements]]
id = "REQ-1"
outcome = "Retain the original behavior."
acceptance = ["The behavioral evidence remains available."]
[change.execution]
[[change.execution.steps]]
id = "STEP-1"
requirements = ["REQ-1"]
action = "Use the existing behavior owner."
'''
    digest = contract_digest(parse_change_record(source).contract)
    source += f'''[change.approval]
actor = "Owner"
recorded_at = 2026-10-29
source = "Owner confirmed the fixture contract."
contract_digest = "{digest}"
'''
    path = tmp_path / "changes/alpha/change.toml"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    git_output(tmp_path, "add", ".")
    git_output(tmp_path, "commit", "-m", "approve alpha")
    return tmp_path


def request(repository, store, identity="alpha/first", **fields):
    record = parse_change_record((repository / "changes/alpha/change.toml").read_text())
    return store.parse_request(
        {
            "approval_digest": contract_digest(record.contract),
            "id": identity,
            "change_id": "alpha",
            "operation": "record",
            "reason": "Keep a significant implementation observation.",
            "observations": [
                {
                    "id": identity + "/observation",
                    "requirements": ["REQ-1"],
                    "summary": "The behavior owner already supplies the required result.",
                    "reason": "Avoid repeating the same investigation.",
                    "evidence": ["behavior.py"],
                }
            ],
            **fields,
        }
    )


@pytest.mark.parametrize("store", ["engine", "template"], indirect=True)
def test_approved_append_and_exact_retry_preserve_source_and_derive_current_state(
    repository, store
):
    before = store.snapshot(repository)
    transaction = request(repository, store)
    after = store.append_transaction(
        repository, transaction, expected_history=before.history_digest
    )
    history = repository / "changes/alpha/events.jsonl"
    encoded = history.read_bytes()
    assert len(encoded.splitlines()) == 1
    assert after.observations[0].status == "pending"
    assert after.observations[0].observation.reason == "Avoid repeating the same investigation."
    assert after.working_set.clauses == ()
    assert (
        store.append_transaction(repository, transaction, expected_history=before.history_digest)
        == after
    )
    assert history.read_bytes() == encoded


def test_unapproved_or_dirty_behavior_cannot_authorize_writes(repository, store):
    initial = store.snapshot(repository)
    transaction = request(repository, store)
    path = repository / "changes/alpha/change.toml"
    path.write_text(
        path.read_text().replace("Retain the original behavior.", "Different behavior.")
    )
    with pytest.raises(ValueError):
        store.append_transaction(repository, transaction, expected_history=initial.history_digest)
    assert not (path.parent / "events.jsonl").exists()


def test_stale_history_and_conflicting_retry_do_not_change_existing_bytes(repository, store):
    initial = store.snapshot(repository)
    store.append_transaction(
        repository, request(repository, store), expected_history=initial.history_digest
    )
    history = repository / "changes/alpha/events.jsonl"
    before = history.read_bytes()
    with pytest.raises(ValueError):
        store.append_transaction(
            repository,
            request(repository, store, "alpha/second"),
            expected_history=initial.history_digest,
        )
    with pytest.raises(ValueError):
        store.append_transaction(
            repository,
            request(repository, store, reason="Changed payload."),
            expected_history=store.snapshot(repository).history_digest,
        )
    assert history.read_bytes() == before


@pytest.mark.parametrize("store", ["engine", "template"], indirect=True)
def test_atomic_reconciliation_rolls_back_all_changes_on_an_invalid_target(repository, store):
    initial = store.snapshot(repository)
    first = request(repository, store)
    store.append_transaction(repository, first, expected_history=initial.history_digest)
    history = repository / "changes/alpha/events.jsonl"
    before = history.read_bytes()
    candidate = request(
        repository,
        store,
        "alpha/reconcile",
        operation="reconcile",
        resolutions=[
            {
                "id": "alpha/resolve-one",
                "target": first.observations[0].id,
                "status": "resolved",
                "reason": "The behavioral test proves the result.",
                "evidence": ["behavior.py"],
            },
            {
                "id": "alpha/resolve-missing",
                "target": "alpha/unknown",
                "status": "rejected",
                "reason": "This target does not exist.",
            },
        ],
    )
    with pytest.raises(ValueError):
        store.append_transaction(
            repository, candidate, expected_history=store.snapshot(repository).history_digest
        )
    assert history.read_bytes() == before
    assert store.snapshot(repository).observations[0].status == "pending"


def test_committed_journal_prefix_cannot_be_rewritten_or_deleted(repository, store):
    state = store.snapshot(repository)
    store.append_transaction(
        repository, request(repository, store), expected_history=state.history_digest
    )
    history = repository / "changes/alpha/events.jsonl"
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain first event")
    original = history.read_bytes()
    history.write_bytes(original.replace(b"Avoid repeating", b"Altered history"))
    with pytest.raises(ValueError):
        store.snapshot(repository)
    history.unlink()
    with pytest.raises(ValueError):
        store.snapshot(repository)


def _approve(repository, source, change_id="alpha"):
    source = source.split("[change.approval]")[0]
    digest = contract_digest(parse_change_record(source).contract)
    source += f'''[change.approval]
actor = "Owner"
recorded_at = 2026-10-29
source = "Owner confirmed this exact revised contract."
contract_digest = "{digest}"
'''
    path = repository / f"changes/{change_id}/change.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "approve exact revised contract")
    return path


def _inline(value):
    if isinstance(value, dict):
        return "{" + ",".join(f"{key}={_inline(item)}" for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_inline(item) for item in value) + "]"
    return json.dumps(value)


def _decision():
    authority = "changes/alpha/change.toml#decisions/alpha/initial"
    return {
        "id": "alpha/initial",
        "change_id": "alpha",
        "authority": authority,
        "reason": "Keep current decisions reviewable without repeating the original investigation.",
        "topics": [
            {
                "expected_version": 0,
                "revision": {
                    "id": "validation",
                    "version": 1,
                    "summary": "Validation proves the observed source.",
                    "boundaries": ["A successful test does not authorize publication."],
                },
            }
        ],
        "clauses": [
            {
                "id": "alpha/initial-clauses",
                "change_id": "alpha",
                "action": "add",
                "expected": [{"id": "VAL-001", "version": 0}],
                "updates": [
                    {
                        "id": "VAL-001",
                        "version": 1,
                        "topic": "validation",
                        "scope": ["repository"],
                        "statement": "Keep failed validation failed.",
                        "rationale": "A narrower retry is diagnostic evidence.",
                    }
                ],
                "reason": "Preserve the first failed result.",
                "authority": authority,
            }
        ],
    }


@pytest.mark.parametrize("store", ["engine", "template"], indirect=True)
def test_exact_approved_decision_updates_the_generated_current_set(repository, store):
    proposal = _decision()
    path = repository / "changes/alpha/change.toml"
    source = path.read_text().replace(
        "[change.contract]\n", "[change.contract]\ndecisions=" + _inline([proposal]) + "\n"
    )
    _approve(repository, source)
    transaction = request(
        repository, store, "alpha/accept", operation="reconcile", decisions=[proposal]
    )
    state = store.append_transaction(
        repository, transaction, expected_history=store.snapshot(repository).history_digest
    )
    assert state.working_set.clauses[0].revision.statement == "Keep failed validation failed."
    assert state.working_set.topics[0].revision.boundaries == (
        "A successful test does not authorize publication.",
    )
    assert state.entries[0].approval.blob
    assert not (repository / "docs/decisions").exists()
    assert store.snapshot(repository) == state
    refinement = json.loads(json.dumps(proposal))
    refinement["id"] = "alpha/refinement"
    refinement["authority"] = "changes/alpha/change.toml#decisions/alpha/refinement"
    refinement["parents"] = [proposal["id"]]
    refinement["topics"] = []
    edit = refinement["clauses"][0]
    edit["id"] = "alpha/refinement-clauses"
    edit["authority"] = refinement["authority"]
    edit["action"] = "amend"
    edit["expected"][0]["version"] = 1
    edit["updates"][0]["version"] = 2
    edit["updates"][0]["statement"] = "A diagnostic retry preserves the original failure."
    _approve(
        repository,
        path.read_text().replace(
            "decisions=" + _inline([proposal]), "decisions=" + _inline([proposal, refinement])
        ),
    )
    arguments = (
        "reconcile",
        "--id",
        "accept-refinement",
        "--reason",
        "Apply only new exact proposals.",
        "--accept-decisions",
    )
    for _ in range(2):
        applied = _cli(repository, store, *arguments)
        assert applied.returncode == 0, applied.stdout + applied.stderr
        assert json.loads(applied.stdout)["decision_transactions"] == [refinement["id"]]
    revised = store.snapshot(repository)
    assert len(revised.entries) == 2
    assert revised.working_set.clauses[0].revision.version == 2


def test_unapproved_decision_bytes_cannot_enter_the_current_set(repository, store):
    proposal = _decision()
    path = repository / "changes/alpha/change.toml"
    source = path.read_text().replace(
        "[change.contract]\n", "[change.contract]\ndecisions=" + _inline([proposal]) + "\n"
    )
    _approve(repository, source)
    proposal["clauses"][0]["updates"][0]["statement"] = "Treat a failed test as passed."
    transaction = request(
        repository, store, "alpha/altered", operation="reconcile", decisions=[proposal]
    )
    with pytest.raises(ValueError, match="exact approved"):
        store.append_transaction(
            repository, transaction, expected_history=store.snapshot(repository).history_digest
        )
    assert not (path.parent / "events.jsonl").exists()
    assert store.snapshot(repository).working_set.clauses == ()


@pytest.mark.parametrize("operation,status", [("resolve", "resolved"), ("resolve", "rejected")])
def test_terminal_dispositions_retain_the_original_observation(
    repository, store, operation, status
):
    first = request(repository, store)
    state = store.append_transaction(
        repository, first, expected_history=store.snapshot(repository).history_digest
    )
    path = repository / "changes/alpha/events.jsonl"
    original = path.read_bytes()
    resolution = request(
        repository,
        store,
        "alpha/finish",
        operation=operation,
        observations=[],
        resolutions=[
            {
                "id": "alpha/disposition",
                "target": first.observations[0].id,
                "status": status,
                "reason": "Retain the evidence and the disposition rationale.",
                "evidence": ["behavior.py"],
            }
        ],
    )
    result = store.append_transaction(repository, resolution, expected_history=state.history_digest)
    assert path.read_bytes().startswith(original)
    assert result.observations[0].observation == first.observations[0]
    assert result.observations[0].status == status
    with pytest.raises(ValueError):
        store.append_transaction(
            repository,
            request(
                repository,
                store,
                "alpha/repeat",
                operation=operation,
                observations=[],
                resolutions=[
                    {
                        "id": "alpha/repeated-disposition",
                        "target": first.observations[0].id,
                        "status": status,
                        "reason": "Cannot close it a second time.",
                        "evidence": ["behavior.py"],
                    }
                ],
            ),
            expected_history=result.history_digest,
        )
    assert store.snapshot(repository) == result


@pytest.mark.parametrize(
    "damage",
    ["draft", "complete", "base", "missing", "symlink", "ignored", "unknown_requirement", "batch"],
)
def test_invalid_authority_never_creates_a_journal(repository, store, damage, tmp_path):
    path = repository / "changes/alpha/change.toml"
    transaction = request(repository, store)
    if damage == "draft":
        path.write_text(path.read_text().split("[change.approval]")[0])
        git_output(repository, "commit", "-am", "draft has no approval")
    elif damage == "complete":
        path.write_text(
            path.read_text().replace('id = "alpha"', 'id = "alpha"\nstatus = "complete"', 1)
        )
        git_output(repository, "commit", "-am", "close change")
    elif damage == "base":
        old = parse_change_record(path.read_text()).contract.approved_base
        current = git_output(repository, "rev-parse", "HEAD")
        _approve(repository, path.read_text().replace(old, current))
    elif damage == "missing":
        git_output(repository, "rm", str(path))
        git_output(repository, "commit", "-m", "remove authority")
    elif damage == "symlink":
        target = repository / "external-history"
        target.write_text("do not overwrite\n")
        (path.parent / "events.jsonl").symlink_to(target)
    elif damage == "ignored":
        (repository / ".gitignore").write_text("events.jsonl\n")
    elif damage == "unknown_requirement":
        transaction = request(
            repository,
            store,
            observations=[
                {
                    "id": "alpha/unknown",
                    "requirements": ["UNKNOWN"],
                    "summary": "Outside scope.",
                    "reason": "No approval exists.",
                }
            ],
        )
    else:
        branch = "batch/probe"
        git_output(repository, "switch", "-c", branch)
        common = Path(
            git_output(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        write_record(
            common / "signetum",
            WorkspaceRecord(1, branch, git_output(repository, "rev-parse", "HEAD"), "batch"),
        )
    with pytest.raises(ValueError):
        store.append_transaction(
            repository, transaction, expected_history=store.snapshot(repository).history_digest
        )
    if damage == "symlink":
        assert (repository / "external-history").read_text() == "do not overwrite\n"
    else:
        assert not (path.parent / "events.jsonl").exists()


def test_historical_approval_remains_readable_after_the_change_is_closed(repository, store):
    first = request(repository, store)
    state = store.append_transaction(
        repository, first, expected_history=store.snapshot(repository).history_digest
    )
    path = repository / "changes/alpha/change.toml"
    path.write_text(
        path.read_text().replace('id = "alpha"', 'id = "alpha"\nstatus = "complete"', 1)
    )
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "close source after retaining the journal")
    assert store.snapshot(repository) == state
    with pytest.raises(ValueError):
        store.append_transaction(
            repository,
            request(repository, store, "alpha/later"),
            expected_history=state.history_digest,
        )


def test_ordinary_plan_refinement_does_not_request_new_behavior_approval(repository, store):
    path = repository / "changes/alpha/change.toml"
    path.write_text(
        path.read_text().replace(
            "Use the existing behavior owner.", "Use the same owner with a narrower test."
        )
    )
    state = store.append_transaction(
        repository,
        request(repository, store),
        expected_history=store.snapshot(repository).history_digest,
    )
    assert len(state.entries) == 1
    assert "narrower test" in path.read_text()


@pytest.mark.parametrize("store", ["engine", "template"], indirect=True)
def test_concurrent_writer_refuses_instead_of_waiting_or_appending(repository, store):
    common = Path(git_output(repository, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    with (common / "signetum/development.lock").open("a+b") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="writer is active"):
            store.append_transaction(
                repository,
                request(repository, store),
                expected_history=store.snapshot(repository).history_digest,
            )
    assert not (repository / "changes/alpha/events.jsonl").exists()


def _followup(repository):
    source = (repository / "changes/alpha/change.toml").read_text()
    return _approve(repository, source.replace('id = "alpha"', 'id = "beta"', 1), "beta")


def test_deferral_requires_an_explicit_approved_transfer_and_an_active_requirement(
    repository, store
):
    first = request(repository, store)
    state = store.append_transaction(
        repository, first, expected_history=store.snapshot(repository).history_digest
    )
    _followup(repository)
    resolution = request(
        repository,
        store,
        "alpha/defer",
        operation="resolve",
        observations=[],
        resolutions=[
            {
                "id": "alpha/followup",
                "target": first.observations[0].id,
                "status": "deferred",
                "reason": "Owner moved this requirement to the explicit follow-up.",
                "followup": "beta#REQ-1",
            }
        ],
    )
    with pytest.raises(ValueError, match="human-approved requirement transfer"):
        store.append_transaction(repository, resolution, expected_history=state.history_digest)
    path = repository / "changes/alpha/change.toml"
    revised = (
        path.read_text()
        .replace('id = "REQ-1"', 'id = "REQ-2"')
        .replace('requirements = ["REQ-1"]', 'requirements = ["REQ-2"]')
    )
    revised = revised.replace(
        "[change.execution]",
        '[[change.contract.transferred]]\nid="REQ-1"\nstatement="Original requirement."\n'
        'target="beta/REQ-1"\n[change.execution]',
    )
    _approve(repository, revised)
    with pytest.raises(ValueError, match="approval changed"):
        store.append_transaction(repository, resolution, expected_history=state.history_digest)
    resolution = store.parse_request(
        {
            **contract_mapping(resolution),
            "approval_digest": contract_digest(parse_change_record(path.read_text()).contract),
        }
    )
    result = store.append_transaction(repository, resolution, expected_history=state.history_digest)
    assert result.observations[0].status == "deferred"
    assert result.observations[0].resolution.followup == "beta#REQ-1"
    assert store.snapshot(repository) == result
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain the exact approved deferral")
    summary = store.reconciliation_summary(
        repository, ("alpha",), commit=git_output(repository, "rev-parse", "HEAD")
    )
    assert summary["changes"][0]["observations"][0]["status"] == "deferred"
    following = repository / "changes/beta/change.toml"
    following.write_text(
        following.read_text().replace("[change]", '[change]\nstatus = "withdrawn"', 1)
    )
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "withdraw the follow-up")
    with pytest.raises(ValueError, match="active owning change"):
        store.reconciliation_summary(
            repository, ("alpha",), commit=git_output(repository, "rev-parse", "HEAD")
        )


def test_retirement_preserves_the_original_resolution_and_retains_other_evidence(repository, store):
    (repository / "retained.py").write_text("assert True\n")
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain independent evidence")
    first = request(repository, store)
    state = store.append_transaction(
        repository, first, expected_history=store.snapshot(repository).history_digest
    )
    answer = request(
        repository,
        store,
        "alpha/finish",
        operation="resolve",
        observations=[],
        resolutions=[
            {
                "id": "alpha/answer",
                "target": first.observations[0].id,
                "status": "resolved",
                "reason": "The original behavioral evidence proved this result.",
                "evidence": ["behavior.py", "retained.py"],
            }
        ],
    )
    state = store.append_transaction(repository, answer, expected_history=state.history_digest)
    original_resolution = state.observations[0].resolution
    path = repository / "changes/alpha/change.toml"
    old_history = (path.parent / "events.jsonl").read_bytes()
    path.write_text(
        path.read_text().replace('id = "alpha"', 'id = "alpha"\nstatus = "complete"', 1)
    )
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "close original delivery history")
    base = git_output(repository, "rev-parse", "HEAD")
    git_output(repository, "switch", "-c", "plan/beta")
    common = Path(git_output(repository, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    write_record(common / "signetum", WorkspaceRecord(1, "plan/beta", base, "member"))
    retirement = {
        "id": "beta/retire-evidence",
        "target": first.observations[0].id,
        "resolution_id": "alpha/answer",
        "targets": ["behavior.py"],
        "reason": "Owner approved removal of obsolete evidence; the original result is unchanged.",
    }
    source = (
        path.read_text()
        .replace('id = "alpha"', 'id = "beta"', 1)
        .replace('status = "complete"', 'status = "active"')
    )
    source = source.replace(parse_change_record(source).contract.approved_base, base)
    source = source.replace(
        "[change.contract]\n", "[change.contract]\nretirements=" + _inline([retirement]) + "\n"
    )
    beta = _approve(repository, source, "beta")
    transaction = store.parse_request(
        {
            "id": "beta/retire",
            "change_id": "beta",
            "operation": "retire",
            "approval_digest": contract_digest(parse_change_record(beta.read_text()).contract),
            "reason": "Record the approved evidence deletion without reimplementing old work.",
            "retirements": [retirement],
        }
    )
    with pytest.raises(ValueError, match="committed evidence deletion"):
        store.append_transaction(repository, transaction, expected_history=state.history_digest)
    git_output(repository, "rm", "behavior.py")
    git_output(repository, "commit", "-m", "remove the approved obsolete evidence")
    result = store.append_transaction(
        repository, transaction, expected_history=state.history_digest
    )
    current = result.observations[0]
    assert current.status == "resolved"
    assert current.resolution == original_resolution
    assert current.effective_evidence == ("retained.py", "changes/beta/change.toml")
    assert current.retirements[0].retirement.targets == ("behavior.py",)
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain the approved evidence retirement")
    summary = store.reconciliation_summary(
        repository, ("beta",), commit=git_output(repository, "rev-parse", "HEAD")
    )
    assert summary["observation_count"] == 1
    historical = next(row for row in summary["changes"] if row["change_id"] == "alpha")
    assert historical["observations"][0]["status"] == "resolved"
    assert historical["observations"][0]["retirements"][0]["retirement"]["id"] == retirement["id"]
    assert (path.parent / "events.jsonl").read_bytes() == old_history
    assert store.snapshot(repository) == result


@pytest.mark.parametrize("damage", ["incomplete", "chain", "approval", "unknown_field"])
def test_tampered_uncommitted_journal_is_refused_on_read(repository, store, damage):
    state = store.append_transaction(
        repository,
        request(repository, store),
        expected_history=store.snapshot(repository).history_digest,
    )
    path = repository / "changes/alpha/events.jsonl"
    value = json.loads(path.read_text())
    if damage == "incomplete":
        path.write_bytes(path.read_bytes().rstrip(b"\n"))
    else:
        if damage == "chain":
            value["sequence"] = 3
        elif damage == "approval":
            value["approval"]["blob"] = "0" * 40
        else:
            value["hidden_override"] = True
        path.write_text(json.dumps(value) + "\n")
    with pytest.raises(ValueError):
        store.snapshot(repository)
    assert state.observations[0].status == "pending"


def test_failed_atomic_replace_preserves_history_and_exact_retry_is_available(
    repository, store, monkeypatch
):
    state = store.append_transaction(
        repository,
        request(repository, store),
        expected_history=store.snapshot(repository).history_digest,
    )
    path = repository / "changes/alpha/events.jsonl"
    before = path.read_bytes()
    original = store.os.replace

    def fail_replace(*_):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failure"):
        store.append_transaction(
            repository,
            request(repository, store, "alpha/next"),
            expected_history=state.history_digest,
        )
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".events-*"))
    monkeypatch.setattr(store.os, "replace", original)
    result = store.append_transaction(
        repository, request(repository, store, "alpha/next"), expected_history=state.history_digest
    )
    assert len(result.entries) == 2


def _cli(repository, store, *arguments, isolated=None):
    root = Path(__file__).parents[2]
    engine = store.__name__.startswith("signetum.")
    if isolated is None:
        isolated = not engine
    runtime = root / "src" if engine else root / "template/.agents/repo-dev/runtime"
    script = (
        "import importlib,sys; sys.path.insert(0,sys.argv.pop(1)); "
        "module=importlib.import_module(sys.argv.pop(1)); "
        "result=module.main(sys.argv[1:]); "
        "assert 'pydantic' not in sys.modules; "
        + ("" if engine else "assert 'signetum' not in sys.modules; ")
        + "raise SystemExit(result)"
    )
    return subprocess.run(  # noqa: S603 -- isolated interpreter, fixture-owned argv
        [
            sys.executable,
            *(["-I", "-S"] if isolated else []),
            "-c",
            script,
            str(runtime),
            store.__name__,
            *arguments,
            "--repository",
            str(repository),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("isolated", [False, True])
@pytest.mark.parametrize("store", ["engine", "template"], indirect=True)
def test_real_cli_mutation_and_lazy_read_views_need_no_engine_installation(
    repository, store, isolated
):
    before = store.snapshot(repository)
    transaction = request(repository, store)
    input_path = repository / "request.json"
    input_path.write_text(json.dumps(contract_mapping(transaction)))
    result = _cli(
        repository,
        store,
        "record",
        "--request",
        str(input_path),
        "--expected-history",
        before.history_digest,
        isolated=isolated,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["observations"][0]["status"] == "pending"
    original = (repository / "changes/alpha/events.jsonl").read_bytes()
    status = git_output(repository, "status", "--porcelain")
    legacy = repository / "docs/decisions/ADP-existing.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("# Existing rule\nStatus: Accepted\nSupersedes: None\nSuperseded by: None\n")
    git_output(repository, "add", str(legacy.relative_to(repository)))
    git_output(repository, "commit", "-m", "retain existing decision")
    current = _cli(repository, store, "current", isolated=isolated)
    assert current.returncode == 0, current.stderr
    assert {
        "schema_version",
        "status",
        "history_digest",
        "working_set",
        "authority_coverage",
    } <= json.loads(current.stdout).keys()
    historical = json.loads(current.stdout)["historical_authorities"]
    assert historical[0]["path"] == "docs/decisions/ADP-existing.md"
    assert historical[0]["standing"] == "retained"
    assert historical[0]["blob"] == git_output(
        repository, "rev-parse", "HEAD:docs/decisions/ADP-existing.md"
    )
    listing = _cli(repository, store, "status", isolated=isolated)
    assert listing.returncode == 0, listing.stderr
    assert "entries" not in json.loads(listing.stdout)
    history = _cli(
        repository, store, "history", "--event", transaction.observations[0].id, isolated=isolated
    )
    assert history.returncode == 0, history.stderr
    assert json.loads(history.stdout)["entries"][0]["transaction"]["id"] == transaction.id
    change_history = _cli(repository, store, "history", "--change", "alpha", isolated=isolated)
    assert json.loads(change_history.stdout) == json.loads(history.stdout)
    assert (repository / "changes/alpha/events.jsonl").read_bytes() == original
    assert git_output(repository, "status", "--porcelain") == status


@pytest.mark.parametrize(
    "arguments",
    [
        ["record"],
        ["history"],
        ["history", "--event", "alpha/missing"],
        ["current", "--expected-history", "invalid"],
        ["status", "--change", "alpha"],
    ],
)
def test_invalid_cli_requests_are_structured_and_never_write_source(repository, store, arguments):
    result = _cli(repository, store, *arguments)
    assert result.returncode == 2
    assert len(result.stdout.splitlines()) == 1
    assert json.loads(result.stdout)["status"] == "invalid"
    assert not (repository / "changes/alpha/events.jsonl").exists()


@pytest.mark.parametrize(
    "damage",
    [
        "empty",
        "namespace",
        "duplicate",
        "duplicate_requirement",
        "wrong_operation",
        "wrong_disposition",
        "missing_followup",
        "unexpected_followup",
        "missing_evidence",
    ],
)
def test_invalid_requests_are_refused_before_any_source_write(repository, store, damage):
    value = json.loads(json.dumps(contract_mapping(request(repository, store))))
    if damage == "empty":
        value["observations"] = []
    elif damage == "namespace":
        value["id"] = "other/change"
    elif damage == "duplicate":
        value["observations"] *= 2
    elif damage == "duplicate_requirement":
        value["observations"][0]["requirements"] *= 2
    else:
        resolution = {
            "id": "alpha/terminal",
            "target": "alpha/first/observation",
            "status": "resolved",
            "reason": "Explain the disposition.",
            "evidence": ["behavior.py"],
        }
        value["resolutions"] = [resolution]
        if damage != "wrong_operation":
            value["operation"] = "resolve"
            value["observations"] = []
        if damage == "wrong_disposition":
            value["operation"] = "retract"
        elif damage == "missing_followup":
            resolution["status"] = "deferred"
        elif damage == "unexpected_followup":
            resolution["followup"] = "beta#REQ-1"
        elif damage == "missing_evidence":
            resolution["evidence"] = []
    with pytest.raises(ValueError):
        store.parse_request(value)
    assert not (repository / "changes/alpha/events.jsonl").exists()


def test_a_second_member_cannot_claim_the_same_change(repository, store):
    state = store.append_transaction(
        repository,
        request(repository, store),
        expected_history=store.snapshot(repository).history_digest,
    )
    branch = "plan/intruder"
    base = parse_change_record(
        (repository / "changes/alpha/change.toml").read_text()
    ).contract.approved_base
    git_output(repository, "switch", "-c", branch)
    common = Path(git_output(repository, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    write_record(common / "signetum", WorkspaceRecord(1, branch, base, "member"))
    history = repository / "changes/alpha/events.jsonl"
    original = history.read_bytes()
    with pytest.raises(ValueError, match="already belongs"):
        store.append_transaction(
            repository,
            request(repository, store, "alpha/stolen"),
            expected_history=state.history_digest,
        )
    assert history.read_bytes() == original


@pytest.mark.parametrize("damage", ["operation", "filter"])
def test_cli_does_not_apply_a_request_under_a_different_operation_or_history_filter(
    repository, store, damage
):
    state = store.snapshot(repository)
    path = repository / "request.json"
    path.write_text(json.dumps(contract_mapping(request(repository, store))))
    arguments = [
        "reconcile" if damage == "operation" else "record",
        "--request",
        str(path),
        "--expected-history",
        state.history_digest,
    ]
    if damage == "filter":
        arguments.extend(["--change", "alpha"])
    result = _cli(repository, store, *arguments)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "invalid"
    assert not (repository / "changes/alpha/events.jsonl").exists()


def test_a_stale_request_cannot_be_relabelled_with_a_new_approval(repository, store):
    transaction = request(repository, store)
    state = store.snapshot(repository)
    path = repository / "changes/alpha/change.toml"
    revised = (
        path.read_text()
        .replace("Retain the original behavior.", "A separately approved revised behavior.")
        .replace("[change.contract]\nversion = 1", "[change.contract]\nversion = 2", 1)
    )
    _approve(repository, revised)
    with pytest.raises(ValueError, match="approval"):
        store.append_transaction(repository, transaction, expected_history=state.history_digest)
    assert not (path.parent / "events.jsonl").exists()


@pytest.mark.parametrize("standing", ["Accepted", "Proposed", "missing", "outside"])
def test_legacy_standalone_acceptance_is_checked_at_its_original_commit(
    repository, store, standing
):
    proposal = _decision()
    relative = "README.md" if standing == "outside" else "docs/decisions/AD-1.md"
    proposal["authority"] = relative
    proposal["clauses"][0]["authority"] = relative
    authority = repository / relative
    if standing != "missing":
        authority.parent.mkdir(parents=True, exist_ok=True)
        authority.write_text(f"# Validation boundary\n\nStatus: {standing}\n")
    path = repository / "changes/alpha/change.toml"
    source = path.read_text().replace(
        "[change.contract]\n", "[change.contract]\ndecisions=" + _inline([proposal]) + "\n"
    )
    _approve(repository, source)
    transaction = request(
        repository, store, "alpha/legacy", operation="reconcile", decisions=[proposal]
    )
    state = store.snapshot(repository)
    if standing != "Accepted":
        with pytest.raises(ValueError):
            store.append_transaction(repository, transaction, expected_history=state.history_digest)
        assert not (path.parent / "events.jsonl").exists()
    else:
        result = store.append_transaction(
            repository, transaction, expected_history=state.history_digest
        )
        authority.write_text("# Historical declaration\n\nStatus: Rejected\n")
        git_output(repository, "add", ".")
        git_output(
            repository, "commit", "-m", "later legacy declaration does not rewrite old acceptance"
        )
        assert store.snapshot(repository) == result


def test_an_observation_identity_cannot_be_reused_in_a_later_transaction(repository, store):
    first = request(repository, store)
    state = store.append_transaction(
        repository, first, expected_history=store.snapshot(repository).history_digest
    )
    next_request = request(
        repository, store, "alpha/duplicate", observations=[contract_mapping(first.observations[0])]
    )
    before = (repository / "changes/alpha/events.jsonl").read_bytes()
    with pytest.raises(ValueError, match="duplicate identity"):
        store.append_transaction(repository, next_request, expected_history=state.history_digest)
    assert (repository / "changes/alpha/events.jsonl").read_bytes() == before


def test_repository_declared_change_root_is_the_only_source_journal_location(repository, store):
    source = (Path(__file__).parents[2] / "signetum.toml").read_text()
    source = source.replace('changes = "changes"', 'changes = "work"').replace(
        'decisions = "docs/decisions"', 'decisions = "authorities"'
    )
    (repository / "signetum.toml").write_text(source)
    (repository / "changes").rename(repository / "work")
    git_output(repository, "add", "-A")
    git_output(repository, "commit", "-m", "declare repository-owned authority roots")
    record = parse_change_record((repository / "work/alpha/change.toml").read_text())
    transaction = store.parse_request(
        {
            "id": "alpha/configured",
            "change_id": "alpha",
            "approval_digest": contract_digest(record.contract),
            "operation": "record",
            "reason": "Honor the declared repository authority.",
            "observations": [
                {
                    "id": "alpha/configured-observation",
                    "requirements": ["REQ-1"],
                    "summary": "Use the declared change root.",
                    "reason": "No undeclared default root is an authority.",
                }
            ],
        }
    )
    result = store.append_transaction(
        repository, transaction, expected_history=store.snapshot(repository).history_digest
    )
    assert result.entries[0].approval.path == "work/alpha/change.toml"
    assert (repository / "work/alpha/events.jsonl").is_file()
    assert not (repository / "changes").exists()
    response = _cli(repository, store, "current")
    assert response.returncode == 0, response.stderr


def test_a_commit_change_during_a_read_refuses_the_mixed_snapshot(repository, store, monkeypatch):
    state = store.append_transaction(
        repository,
        request(repository, store),
        expected_history=store.snapshot(repository).history_digest,
    )
    original = store._read_journal
    changed = []

    def read_and_commit(*arguments):
        result = original(*arguments)
        if not changed:
            git_output(repository, "commit", "--allow-empty", "-m", "concurrent committed source")
            changed.append(True)
        return result

    monkeypatch.setattr(store, "_read_journal", read_and_commit)
    with pytest.raises(ValueError, match="source commit changed"):
        store.snapshot(repository)
    monkeypatch.setattr(store, "_read_journal", original)
    assert store.snapshot(repository) == state


def test_a_commit_change_during_write_validation_never_appends(repository, store, monkeypatch):
    state = store.snapshot(repository)
    original = store.claim_change

    def claim_and_commit(*arguments):
        original(*arguments)
        git_output(repository, "commit", "--allow-empty", "-m", "concurrent commit before append")

    monkeypatch.setattr(store, "claim_change", claim_and_commit)
    with pytest.raises(ValueError, match="source commit changed"):
        store.append_transaction(
            repository, request(repository, store), expected_history=state.history_digest
        )
    assert not (repository / "changes/alpha/events.jsonl").exists()


def _resolved(repository, store):
    first = request(repository, store)
    state = store.append_transaction(
        repository, first, expected_history=store.snapshot(repository).history_digest
    )
    answer = request(
        repository,
        store,
        "alpha/answer-event",
        operation="resolve",
        observations=[],
        resolutions=[
            {
                "id": "alpha/answer",
                "target": first.observations[0].id,
                "status": "resolved",
                "reason": "Initial evidence appeared to establish the result.",
                "evidence": ["behavior.py"],
            }
        ],
    )
    state = store.append_transaction(repository, answer, expected_history=state.history_digest)
    return first, answer, state


def _withdraw(repository, store, target, resolution="alpha/answer", identity="alpha/correction"):
    return request(
        repository,
        store,
        identity,
        operation="retract",
        observations=[],
        retractions=[
            {
                "id": identity + "/withdrawal",
                "target": target,
                "resolution_id": resolution,
                "reason": "The earlier answer was recorded in error; reconsider it independently.",
            }
        ],
    )


def test_retraction_withdraws_only_the_answer_and_returns_the_finding_to_pending(repository, store):
    first, answer, state = _resolved(repository, store)
    path = repository / "changes/alpha/events.jsonl"
    original = path.read_bytes()
    correction = _withdraw(repository, store, first.observations[0].id)
    result = store.append_transaction(repository, correction, expected_history=state.history_digest)
    current = result.observations[0]
    assert current.status == "pending" and current.resolution is None
    assert current.observation == first.observations[0]
    assert current.retractions[0].resolution == answer.resolutions[0]
    assert current.retractions[0].retraction.reason
    assert path.read_bytes().startswith(original)
    with pytest.raises(ValueError, match="standing resolution"):
        store.append_transaction(
            repository,
            _withdraw(repository, store, first.observations[0].id, identity="alpha/repeated"),
            expected_history=result.history_digest,
        )
    illegal = contract_mapping(
        request(
            repository,
            store,
            "alpha/bad-answer",
            operation="resolve",
            observations=[],
            resolutions=[
                {
                    "id": "alpha/bad",
                    "target": first.observations[0].id,
                    "status": "resolved",
                    "reason": "Retraction does not waive evidence requirements.",
                    "evidence": ["behavior.py"],
                }
            ],
        )
    )
    illegal = json.loads(json.dumps(illegal))
    illegal["resolutions"][0]["evidence"] = []
    with pytest.raises(ValueError, match="acceptance evidence"):
        store.parse_request(illegal)
    assert store.snapshot(repository) == result


def test_a_discovery_without_a_standing_answer_cannot_be_retracted(repository, store):
    first = request(repository, store)
    state = store.append_transaction(
        repository, first, expected_history=store.snapshot(repository).history_digest
    )
    with pytest.raises(ValueError, match="standing resolution"):
        store.append_transaction(
            repository,
            _withdraw(repository, store, first.observations[0].id),
            expected_history=state.history_digest,
        )
    assert store.snapshot(repository) == state


def test_atomic_reconciliation_keeps_the_old_answer_if_the_replacement_is_invalid(
    repository, store
):
    first, _, state = _resolved(repository, store)
    correction = _withdraw(repository, store, first.observations[0].id)
    path = repository / "changes/alpha/events.jsonl"
    original = path.read_bytes()
    replacement = {
        "id": "alpha/new-answer",
        "target": "alpha/missing",
        "status": "resolved",
        "reason": "The replacement must be independently valid.",
        "evidence": ["behavior.py"],
    }
    transaction = request(
        repository,
        store,
        "alpha/reconcile-answer",
        operation="reconcile",
        observations=[],
        retractions=[contract_mapping(correction.retractions[0])],
        resolutions=[replacement],
    )
    with pytest.raises(ValueError, match="absent observation"):
        store.append_transaction(repository, transaction, expected_history=state.history_digest)
    assert path.read_bytes() == original
    assert store.snapshot(repository) == state
    replacement["target"] = first.observations[0].id
    transaction = request(
        repository,
        store,
        "alpha/reconcile-answer",
        operation="reconcile",
        observations=[],
        retractions=[contract_mapping(correction.retractions[0])],
        resolutions=[replacement],
    )
    result = store.append_transaction(
        repository, transaction, expected_history=state.history_digest
    )
    assert result.observations[0].resolution.id == "alpha/new-answer"
    assert len(result.observations[0].retractions) == 1
    assert len(result.entries) == len(state.entries) + 1


def test_a_semantically_invalid_old_answer_can_be_repaired_append_only(repository, store):
    first, _, _ = _resolved(repository, store)
    path = repository / "changes/alpha/events.jsonl"
    # Disposable legacy-defect fixture: a prior writer accepted an answer with
    # no evidence. Production repair below uses only the public append API.
    lines = path.read_bytes().splitlines(keepends=True)
    damaged = json.loads(lines[-1])
    damaged["transaction"]["resolutions"][0]["evidence"] = []
    path.write_bytes(b"".join(lines[:-1]) + json.dumps(damaged).encode() + b"\n")
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain the simulated prior-writer defect")
    retained = path.read_bytes()
    with pytest.raises(ValueError, match="acceptance evidence"):
        store.snapshot(repository)
    status = _cli(repository, store, "status")
    assert status.returncode == 2
    failure = json.loads(status.stdout)
    assert failure["history_digest"]
    history = _cli(repository, store, "history", "--event", "alpha/answer")
    assert history.returncode == 0, history.stderr
    correction = _withdraw(repository, store, first.observations[0].id)
    result = store.append_transaction(
        repository, correction, expected_history=failure["history_digest"]
    )
    assert result.observations[0].status == "pending"
    assert result.observations[0].retractions[0].resolution.evidence == ()
    assert path.read_bytes().startswith(retained)
    assert len(path.read_bytes().splitlines()) == 3
    assert store.snapshot(repository) == result


def test_installed_wheel_runs_the_journal_outside_the_source_checkout(
    repository, tmp_path_factory, installed_python
):
    python = installed_python
    root = tmp_path_factory.mktemp("installed-development-journal")
    source = importlib.import_module("signetum.development_store")
    transaction = request(repository, source)
    state = source.snapshot(repository)
    path = repository / "request.json"
    path.write_text(json.dumps(contract_mapping(transaction)))
    for arguments in (
        ["record", "--request", str(path), "--expected-history", state.history_digest],
        ["status"],
        ["history", "--event", transaction.observations[0].id],
    ):
        result = subprocess.run(  # noqa: S603 -- installed public entrypoint and fixture-owned argv
            [
                str(python),
                "-B",
                "-I",
                "-m",
                "signetum.development_store",
                *arguments,
                "--repository",
                str(repository),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "passed"
    assert source.snapshot(repository).observations[0].observation == transaction.observations[0]


@pytest.mark.parametrize("store", ["engine", "template"], indirect=True)
def test_uncommitted_repository_binding_cannot_redirect_journal_authority(repository, store):
    archive = repository / "archive/alpha/change.toml"
    archive.parent.mkdir(parents=True)
    archive.write_bytes((repository / "changes/alpha/change.toml").read_bytes())
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain a non-authoritative archived record")
    state = store.snapshot(repository)
    transaction = request(repository, store)
    source = (Path(__file__).parents[2] / "signetum.toml").read_text()
    source = source.replace('changes = "changes"', 'changes = "archive"')
    (repository / "signetum.toml").write_text(source)
    with pytest.raises(ValueError, match="committed"):
        store.append_transaction(repository, transaction, expected_history=state.history_digest)
    assert not (archive.parent / "events.jsonl").exists()
    assert not (repository / "changes/alpha/events.jsonl").exists()


def test_partially_superseded_legacy_authority_keeps_its_unaffected_clauses(repository, store):
    proposal = _decision()
    relative = "docs/decisions/AD-1.md"
    proposal["authority"] = relative
    proposal["clauses"][0]["authority"] = relative
    directory = repository / "docs/decisions"
    directory.mkdir(parents=True)
    (directory / "AD-1.md").write_text(
        "# Original rules\nStatus: Accepted\nSuperseded by: AD-2.md\n"
    )
    (directory / "AD-2.md").write_text(
        "# Partial change\nStatus: Accepted\nSupersedes: AD-1.md\nPartially supersedes: AD-1.md\n"
    )
    path = repository / "changes/alpha/change.toml"
    _approve(
        repository,
        path.read_text().replace(
            "[change.contract]\n", "[change.contract]\ndecisions=" + _inline([proposal]) + "\n"
        ),
    )
    transaction = request(
        repository, store, "alpha/partial", operation="reconcile", decisions=[proposal]
    )
    result = store.append_transaction(
        repository, transaction, expected_history=store.snapshot(repository).history_digest
    )
    assert result.working_set.clauses[0].revision.id == "VAL-001"


@pytest.mark.parametrize("store", ["engine", "template"], indirect=True)
def test_source_review_binds_committed_history_and_refuses_pending_findings(repository, store):
    initial = store.snapshot(repository)
    store.append_transaction(
        repository, request(repository, store), expected_history=initial.history_digest
    )
    with pytest.raises(ValueError, match="committed"):
        store.review_inputs(
            repository, ("alpha",), commit=git_output(repository, "rev-parse", "HEAD")
        )
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain source observation")
    commit = git_output(repository, "rev-parse", "HEAD")
    inputs = store.review_inputs(repository, ("alpha",), commit=commit)
    assert inputs["journals"]["changes/alpha/events.jsonl"] == git_output(
        repository, "rev-parse", "HEAD:changes/alpha/events.jsonl"
    )
    with pytest.raises(ValueError, match="unresolved source observations"):
        store.reconciliation_summary(repository, ("alpha",), commit=commit)
    assert store.reconciliation_summary(repository, (), commit=commit)["observation_count"] == 0


@pytest.mark.parametrize(
    "outcome", ["resolved", "rejected", "retracted", "missing", "untracked", "complete"]
)
def test_source_reconciliation_preserves_standing_answers_and_frozen_evidence(
    repository, store, outcome
):
    state = store.append_transaction(
        repository,
        request(repository, store),
        expected_history=store.snapshot(repository).history_digest,
    )
    evidence = "probe.txt" if outcome == "untracked" else "behavior.py"
    if outcome == "untracked":
        (repository / evidence).write_text("untracked evidence must not qualify")
    resolution = {
        "id": "alpha/answer",
        "target": "alpha/first/observation",
        "status": "rejected" if outcome == "rejected" else "resolved",
        "reason": "The retained source justifies this disposition.",
        "evidence": [] if outcome == "rejected" else [evidence],
    }
    state = store.append_transaction(
        repository,
        request(
            repository,
            store,
            "alpha/resolve",
            operation="resolve",
            observations=[],
            resolutions=[resolution],
        ),
        expected_history=state.history_digest,
    )
    if outcome == "retracted":
        store.append_transaction(
            repository,
            request(
                repository,
                store,
                "alpha/retract",
                operation="retract",
                observations=[],
                retractions=[
                    {
                        "id": "alpha/withdraw",
                        "target": "alpha/first/observation",
                        "resolution_id": "alpha/answer",
                        "reason": "The answer needs correction.",
                    }
                ],
            ),
            expected_history=state.history_digest,
        )
    if outcome == "missing":
        git_output(repository, "rm", "behavior.py")
    elif outcome == "complete":
        path = repository / "changes/alpha/change.toml"
        path.write_text(path.read_text().replace("[change]", '[change]\nstatus = "complete"', 1))
    git_output(repository, "add", "changes")
    git_output(repository, "commit", "-m", "retain standing source answer")
    commit = git_output(repository, "rev-parse", "HEAD")
    journal = repository / "changes/alpha/events.jsonl"
    before = journal.read_bytes()
    if outcome in {"retracted", "missing", "untracked"}:
        with pytest.raises(ValueError, match=r"unresolved|evidence is absent"):
            store.reconciliation_summary(repository, ("alpha",), commit=commit)
    else:
        summary = store.reconciliation_summary(repository, ("alpha",), commit=commit)
        assert summary["observation_count"] == 1
        expected = "rejected" if outcome == "rejected" else "resolved"
        assert summary["changes"][0]["observations"][0]["status"] == expected
    assert journal.read_bytes() == before
    git_output(repository, "commit", "--allow-empty", "-m", "new source identity")
    with pytest.raises(ValueError, match="commit differs"):
        store.review_inputs(repository, ("alpha",), commit=commit)


@pytest.mark.parametrize("recorded", [False, True])
def test_source_review_requires_exact_approved_decisions_in_committed_history(
    repository, store, recorded
):
    path = repository / "changes/alpha/change.toml"
    proposal = _decision()
    _approve(
        repository,
        path.read_text().replace(
            "[change.contract]\n", "[change.contract]\ndecisions=" + _inline([proposal]) + "\n"
        ),
    )
    if recorded:
        store.append_transaction(
            repository,
            request(
                repository,
                store,
                "alpha/accept",
                operation="reconcile",
                decisions=[proposal],
            ),
            expected_history=store.snapshot(repository).history_digest,
        )
        git_output(repository, "add", ".")
        git_output(repository, "commit", "-m", "retain accepted decision and finding")
    commit = git_output(repository, "rev-parse", "HEAD")
    if recorded:
        view = store.review_inputs(repository, ("alpha",), commit=commit)
        assert view["decision_transactions"] == [proposal["id"]]
    else:
        with pytest.raises(ValueError, match="approved decision is absent"):
            store.review_inputs(repository, ("alpha",), commit=commit)


def test_archived_manifest_locations_are_readable_but_cannot_authorize_new_writes(
    repository, store
):
    current = (Path(__file__).parents[2] / "signetum.toml").read_text()
    transaction = request(repository, store)
    state = store.snapshot(repository)
    archived = current.replace("schema_version = 3", "schema_version = 2", 1).replace(
        'changes = "changes"',
        'specifications = "archive/*/specs/*.toml"\nplans = "archive/*/plans/*.md"',
    )
    manifest = repository / "signetum.toml"
    manifest.write_text(archived)
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain a historical manifest location")
    older = git_output(repository, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="unsupported manifest schema"):
        store.append_transaction(repository, transaction, expected_history=state.history_digest)
    assert not (repository / "archive/alpha/events.jsonl").exists()
    manifest.write_text(current)
    git_output(repository, "commit", "-am", "use the current active manifest")
    assert authority_roots(repository, commit=older, historical=True) == (
        "archive",
        "docs/decisions",
    )
    with pytest.raises(ValueError, match="unsupported manifest schema"):
        authority_roots(repository, commit=older)
    assert store.snapshot(repository).history_digest == state.history_digest
