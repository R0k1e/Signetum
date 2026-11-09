"""Real Git scenarios for an open batch, its siblings and their delivery."""

import json
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest
from change_fixtures import commit_approval
from signetum import change_cli, lifecycle, maintenance
from signetum import manifest as manifest_format
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


def ready_member(root, change_id, name, value="work", *, clause=None, amends=None):
    member = opened(root, f"change/{change_id}")
    if clause is None:
        commit_approval(member, change_id)
    else:
        claim_clause(member, change_id, clause, amends=amends)
    commit_file(member, name, value)
    lifecycle.validate(member, "member")
    return member


def claim_clause(member, change_id, clause, *, amends=None):
    """Add ``clause``, or amend it when ``amends`` names the change that added it."""
    base = lifecycle._recorded_base(member)
    action, version = ("add", 0) if amends is None else ("amend", 1)
    parents = f'parents = ["{amends}/rule"]\n' if amends else ""
    topic = f"{amends or change_id}-topic"
    revision = (
        ""
        if amends
        else f"""[[change.contract.decisions.topics]]
expected_version = 0
[change.contract.decisions.topics.revision]
id = "{topic}"
version = 1
summary = "Fixture rules."
"""
    )
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
{parents}{revision}[[change.contract.decisions.clauses]]
id = "{change_id}/{action}-rule"
change_id = "{change_id}"
action = "{action}"
expected = [{{ id = "{clause}", version = {version} }}]
reason = "Add the rule."
authority = "{authority}"
[[change.contract.decisions.clauses.updates]]
id = "{clause}"
version = {version + 1}
topic = "{topic}"
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
    return Path(
        str(
            lifecycle.batch_open(
                root, (member,), actor="Owner", source="Owner authorized the fixture batch"
            )["worktree"]
        )
    )


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


def older_engine(directory):
    """A Python whose engine identity is the one an older engine reports."""
    wrapper = directory / "older-engine"
    wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = -m ] && [ "$2" = signetum.runtime_identity ]; then\n'
        '  echo \'{"implementation": "older"}\'; exit 0\nfi\n'
        f'exec {shlex.quote(sys.executable)} "$@"\n'
    )
    wrapper.chmod(0o755)
    return str(wrapper)


def ready_under_older_engine(root, monkeypatch, directory, change_id, name):
    with monkeypatch.context() as patched:
        patched.setattr(sys, "executable", older_engine(directory))
        return ready_member(root, change_id, name)


def engine_changing_member(root):
    """A ready member whose manifest uses a field its siblings' manifests do not."""
    member = opened(root, "change/engine")
    commit_approval(member, "engine")
    manifest = member / "signetum.toml"
    manifest.write_text(
        manifest.read_text().replace(
            '[[validation.gates]]\nname = "batch"\nshards = ["test:check"]',
            '[[validation.gates]]\nname = "batch"\nshards = ["test:check", "test:later"]',
        )
        + '[[validation.shards]]\nname = "test:later"\ncommand = ["true"]\nafter = ["test:check"]\n'
    )
    git_output(member, "add", "signetum.toml")
    git_output(member, "commit", "-m", "order a later check")
    lifecycle.validate(member, "member")
    return member


def ready_receipts(member):
    return sorted(path.name for path in lifecycle._receipt_root(member).glob("*-lifecycle-*.json"))


def test_sibling_ready_under_an_older_engine_is_admitted_after_an_engine_change(
    repository, monkeypatch, tmp_path
):
    root, _ = repository
    sibling = ready_under_older_engine(root, monkeypatch, tmp_path, "sibling", "sibling.txt")
    batch = open_batch(root, engine_changing_member(root))
    receipts = ready_receipts(sibling)

    result: Any = lifecycle.admit(batch, (sibling,))

    [admitted] = result["admitted"]
    assert admitted["ready_evidence"] in receipts
    assert ready_receipts(sibling) == receipts
    assert "test:check" in result["static"]["executed"]
    assert (batch / "sibling.txt").exists()


def test_carried_evidence_is_refused_when_the_siblings_own_inputs_changed(
    repository, monkeypatch, tmp_path
):
    root, state = repository
    tool = state / "tool"
    tool.write_text("v1")
    identity = [sys.executable, "-c", "import sys; print(open(sys.argv[1]).read())", str(tool)]
    manifest = root / "signetum.toml"
    manifest.write_text(
        manifest.read_text()
        + '[[validation.tools]]\nname = "fixture"\nidentity_command = '
        + json.dumps(identity)
        + "\n"
    )
    git_output(root, "add", "signetum.toml")
    git_output(root, "commit", "-m", "declare a tool")
    sibling = ready_under_older_engine(root, monkeypatch, tmp_path, "sibling", "sibling.txt")
    batch = open_batch(root, engine_changing_member(root))
    before = git_output(batch, "rev-parse", "HEAD")
    tool.write_text("v2")

    with pytest.raises(AdmissionError, match="no evidence"):
        lifecycle.admit(batch, (sibling,))
    assert git_output(batch, "rev-parse", "HEAD") == before


def test_operations_name_the_supported_path_for_a_newer_batch_manifest(
    repository, monkeypatch, capsys
):
    root, _ = repository
    sibling = ready_member(root, "sibling", "sibling.txt")
    batch = open_batch(root, ready_member(root, "first", "first.txt"))
    # The batch manifest as an engine newer than this one wrote it.
    manifest = batch / "signetum.toml"
    manifest.write_text(manifest.read_text() + "[future]\nsetting = true\n")
    git_output(batch, "add", "signetum.toml")
    git_output(batch, "commit", "-m", "use a newer manifest field")
    monkeypatch.chdir(sibling)
    capsys.readouterr()

    code = lifecycle.main(["batch-admit", "--batch", str(batch), "--member", str(sibling)])

    result = json.loads(capsys.readouterr().out)
    assert code == 2, result
    assert "future" in result["cause"]
    assert "batch workspace" in result["expected"]


def test_a_member_that_synchronized_a_delivered_record_is_admitted_beside_its_amendment(
    repository,
):
    root, _ = repository
    batch_a = open_batch(root, ready_member(root, "first", "first.txt", clause="RULE-001"))
    synchronized = opened(root, "change/synchronized")
    deliver(root, batch_a)
    commit_approval(synchronized, "synchronized")
    commit_file(synchronized, "synchronized.txt")
    ops.workspace_sync(synchronized)
    lifecycle.validate(synchronized, "member")
    amending = ready_member(root, "amending", "amending.txt", clause="RULE-001", amends="first")
    batch = open_batch(root, amending)

    result: Any = lifecycle.admit(batch, (synchronized,))

    assert [item["branch"] for item in result["admitted"]] == ["change/synchronized"]
    assert (batch / "synchronized.txt").exists()


def older_manifest_engine(patched):
    """An engine that still knows the ``legacy`` shard field this engine removed."""
    current = manifest_format.manifest_from_mapping

    def tolerant(data):
        for shard in data.get("validation", {}).get("shards", ()):
            shard.pop("legacy", None)
        return current(data)

    patched.setattr(manifest_format, "manifest_from_mapping", tolerant)


def test_a_member_migrating_an_older_delivered_manifest_is_admitted(
    repository, monkeypatch, capsys
):
    root, _ = repository
    path = root / "signetum.toml"
    path.write_text(
        path.read_text().replace(
            'name = "test:check"\ncommand = ["true"]\n',
            'name = "test:check"\ncommand = ["true"]\nlegacy = ["removed"]\n',
        )
    )
    git_output(root, "commit", "-am", "deliver a manifest an older engine wrote")
    git_output(root, "push", "origin", "main")
    with monkeypatch.context() as patched:
        older_manifest_engine(patched)
        stale = ready_member(root, "stale", "stale.txt")
        migrating = opened(root, "change/migrating")
    commit_approval(migrating, "migrating")
    migrated = migrating / "signetum.toml"
    migrated.write_text(
        migrated.read_text()
        .replace('legacy = ["removed"]\n', "")
        .replace(
            '[[validation.gates]]\nname = "batch"\nshards = ["test:check"]',
            '[[validation.gates]]\nname = "batch"\nshards = ["test:migrated"]',
        )
        + '[[validation.shards]]\nname = "test:migrated"\ncommand = ["true"]\n'
    )
    git_output(migrating, "commit", "-am", "migrate the manifest")
    lifecycle.validate(migrating, "member")

    with pytest.raises(manifest_format.UnsupportedManifestError, match="legacy"):
        lifecycle.batch_open(
            root, (stale,), name="wave", actor="Owner", source="Owner authorized the fixture batch"
        )
    batch = ops.workspace_destination(root, "batch/wave")
    opened_tip = git_output(batch, "rev-parse", "HEAD")
    capsys.readouterr()
    assert change_cli.main(["status", "--repository", str(batch)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["workspace"]["kind"] == "batch"
    assert "legacy" in status["manifest"]["cause"]
    assert "migrates" in status["next"]

    result: Any = lifecycle.admit(batch, (migrating,))

    assert [item["branch"] for item in result["admitted"]] == ["change/migrating"]
    assert result["static"]["executed"] == ["test:migrated"]
    with pytest.raises(manifest_format.UnsupportedManifestError, match="legacy"):
        lifecycle.admit(batch, (stale,))
    assert git_output(batch, "rev-parse", "HEAD^1") == opened_tip
    assert not (batch / "stale.txt").exists()
    capsys.readouterr()
    assert change_cli.main(["status", "--repository", str(batch)]) == 0
    assert "manifest" not in json.loads(capsys.readouterr().out)


def test_a_member_synchronized_from_its_batch_keeps_its_own_change(repository):
    root, _ = repository
    member = ready_member(root, "owned", "owned.txt")
    other = ready_member(root, "other", "other.txt")
    batch = open_batch(root, member)
    lifecycle.admit(batch, (other,))
    ops.workspace_sync(member, batch)
    commit_file(member, "owned-more.txt")

    ready: Any = lifecycle.validate(member, "member")

    assert [item["change_id"] for item in ready["approvals"]] == ["owned"]
    result: Any = lifecycle.admit(batch, (member,))
    assert [item["branch"] for item in result["admitted"]] == ["change/owned"]
    assert (batch / "owned-more.txt").exists()


def test_members_after_a_conflict_are_admitted_by_batch_continue(repository, capsys):
    root, _ = repository
    first = ready_member(root, "first", "shared.txt", "first")
    second = ready_member(root, "second", "shared.txt", "second")
    third = ready_member(root, "third", "third.txt")
    with pytest.raises(MergeConflict) as conflict:
        lifecycle.batch_open(
            root,
            (first, second, third),
            name="wave",
            actor="Owner",
            source="Owner authorized the fixture batch",
        )
    assert "batch-continue" in conflict.value.expected
    assert str(third) in conflict.value.expected
    batch = ops.workspace_destination(root, "batch/wave")
    capsys.readouterr()
    assert change_cli.main(["status", "--repository", str(batch)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["pending_admissions"] == [str(third)]
    assert "batch-continue" in status["next"]
    (batch / "shared.txt").write_text("both")
    git_output(batch, "add", "shared.txt")

    result: Any = lifecycle.continue_batch(batch)

    resumed = result["resumed_admission"]
    assert [item["branch"] for item in resumed["admitted"]] == ["change/third"]
    assert (batch / "third.txt").exists()
    capsys.readouterr()
    assert change_cli.main(["status", "--repository", str(batch)]) == 0
    assert "pending_admissions" not in json.loads(capsys.readouterr().out)


def test_why_gathers_one_clause_with_its_approval_and_commits(repository, capsys):
    root, _ = repository
    member = ready_member(root, "first", "first.txt", clause="RULE-001")
    capsys.readouterr()
    assert change_cli.main(["why", "RULE-001", "--repository", str(member)]) == 0
    explained = json.loads(capsys.readouterr().out)
    [revision] = explained["revisions"]
    assert revision["version"] == 1 and revision["statement"] == "The first rule."
    assert revision["decision_reason"] and revision["edit_reason"]
    [owner] = explained["changes"]
    assert owner["change_id"] == "first"
    assert owner["approval"]["source"] == "Owner confirmed the fixture outcome."
    assert [item["subject"] for item in owner["commits"]] == [
        "accept the first rule",
        "approve change first",
    ]
    assert change_cli.main(["why", "RULE-404", "--repository", str(member)]) != 0
    assert "RULE-404" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["cause"]


def test_a_member_opens_on_an_older_delivered_manifest_and_migrates_it(
    repository, monkeypatch, capsys
):
    root, _ = repository
    path = root / "signetum.toml"
    path.write_text(
        path.read_text().replace(
            'name = "test:check"\ncommand = ["true"]\n',
            'name = "test:check"\ncommand = ["true"]\nlegacy = ["removed"]\n',
        )
    )
    git_output(root, "commit", "-am", "deliver a manifest an older engine wrote")
    git_output(root, "push", "origin", "main")
    capsys.readouterr()
    assert change_cli.main(["status", "--repository", str(root)]) == 0
    assert "legacy" in json.loads(capsys.readouterr().out)["manifest"]["cause"]

    base = git_output(root, "rev-parse", "HEAD")
    opened_result: Any = ops.workspace_open(root, "change/migrating", base)

    assert opened_result["preparation"]["status"] == "unavailable"
    assert "legacy" in opened_result["manifest"]["cause"]
    migrating = Path(str(opened_result["worktree"]))
    with pytest.raises(manifest_format.UnsupportedManifestError, match="legacy"):
        lifecycle.validate(migrating, "member")
    commit_approval(migrating, "migrating")
    migrated = migrating / "signetum.toml"
    migrated.write_text(migrated.read_text().replace('legacy = ["removed"]\n', ""))
    git_output(migrating, "commit", "-am", "migrate the manifest")
    assert lifecycle.validate(migrating, "member")["status"] == "ready"
