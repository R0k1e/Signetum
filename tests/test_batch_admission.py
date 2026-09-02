"""Behavior tests for the bootstrap batch-admission authority."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from shutil import which
from typing import Literal

import pytest

import signetum.lifecycle as lifecycle
from signetum.workspaces import WorkspaceRecord, write_record


def _load_module():
    return lifecycle


def _git(repository: Path, *arguments: str) -> str:
    executable = which("git")
    if executable is None:
        raise RuntimeError("git executable is unavailable")
    return subprocess.run(  # nosec B603
        (executable, "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


MANIFEST = """schema_version = 2

[signetum]
protocol = 2
template_version = "0.2.0"

[repository]
architecture = "docs/ARCHITECTURE.md"
specifications = "changes/*/specs/*.toml"
plans = "changes/*/plans/*.md"
decisions = "docs/decisions"

[[impact.rules]]
name = "everything"
paths = ["**"]
shards = ["repo:check"]

[[impact.rules]]
name = "governance"
paths = ["docs/**"]
requires_final = true

[validation]
member_required = ["repo:check"]

[[validation.shards]]
name = "repo:check"
command = ["true"]

[[validation.gates]]
name = "member"
shards = ["repo:check"]

[[validation.gates]]
name = "final"
shards = ["repo:check"]
"""

MEMBER_COMMAND = ("true",)


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Signetum Tests")
    _git(path, "config", "user.email", "signetum@example.invalid")
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    (path / "signetum.toml").write_text(MANIFEST, encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "seed")
    return path


def _record(
    worktree: Path, branch: str, base: str, kind: Literal["member", "batch"] = "member"
) -> None:
    """Record the base a test workspace was cut from, as workspace-open would."""

    write_record(
        lifecycle._state_root(worktree),
        WorkspaceRecord(schema_version=1, branch=branch, base=base, kind=kind),
    )


def _evidence_receipt(
    member: Path, name: str, *, gate: str, tree: str, commands: tuple[tuple[str, ...], ...]
) -> Path:
    """Write one durable lifecycle receipt proving the given shard commands."""

    evidence = {
        "schema_version": 3,
        "protocol": "reposeal.validation-evidence@3",
        "schema_digest": "sha256:" + "9" * 64,
        "identity": {
            "commit": "a" * 40,
            "tree": tree,
            "base": None,
            "configuration": {"path": "signetum.toml", "digest": "sha256:" + "1" * 64},
            "profiles": [],
            "graph": "sha256:" + "2" * 64,
            "lockfiles": [],
            "tools": [],
        },
        "selection": None,
        "execution": {
            "gates": [gate],
            "shards": [
                {
                    "name": f"repo:proven-{index}",
                    "command_digest": lifecycle.command_digest(command),
                    "evidence": "tree",
                    "status": "passed",
                    "observed_at": None,
                    "waivers": [],
                    "findings": [],
                }
                for index, command in enumerate(commands)
            ],
            "external_obligations": [],
        },
        "completeness": {
            "member": gate == "member",
            "final": gate == "final",
            "required_shards": [f"repo:proven-{index}" for index in range(len(commands))],
            "world_shards": [],
        },
        "provenance": {"stable_patch_id": None},
        "extensions": {},
        "valid": True,
    }
    path = lifecycle._receipt_root(member) / name
    path.write_text(
        json.dumps({"kind": gate, "valid": True, "evidence": evidence}), encoding="utf-8"
    )
    return path


def test_delivery_branch_names_are_refused() -> None:
    module = _load_module()

    assert {"main", "master", "product"}.isdisjoint({"batch/signetum-v2"})
    assert module.AdmissionError


@pytest.mark.parametrize("return_code", [0, 1])
def test_ancestor_query_has_two_valid_outcomes(
    monkeypatch, tmp_path: Path, return_code: int
) -> None:
    module = _load_module()

    class Completed:
        stderr = ""

        def __init__(self, code: int) -> None:
            self.returncode = code

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: Completed(return_code))

    assert module._is_ancestor(tmp_path, "member", "batch") is (return_code == 0)


def test_delivery_finds_the_receipt_bound_to_the_expected_tip(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    source = tmp_path / "source"
    target = tmp_path / "target"
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "final-zzz.json").write_text(
        json.dumps({"source": "older", "valid": True}), encoding="utf-8"
    )
    (receipts / "final-aaa.json").write_text(
        json.dumps({"source": "expected", "base": "base", "valid": True}), encoding="utf-8"
    )

    monkeypatch.setattr(module, "_require_clean", lambda path: None)
    monkeypatch.setattr(module, "_receipt_root", lambda path: receipts)
    monkeypatch.setattr(module, "_branch", lambda path: "main")
    monkeypatch.setattr(module, "_recorded_base", lambda path, branch=None: "base")
    monkeypatch.setattr(module, "_attested_base", lambda path, tip: "base")
    remote_tips = iter(("base", "expected"))
    monkeypatch.setattr(module, "_remote_branch_tip", lambda path, branch: next(remote_tips))
    monkeypatch.setattr(
        module,
        "_delivery_provenance",
        lambda repository, base, tip: (
            [
                {
                    "branch": "member",
                    "original": "member-tip",
                    "integrated": "merge-tip",
                    "summary": "deliver behavior",
                }
            ],
            ["changes/example/plans/example.md"],
        ),
    )
    monkeypatch.setattr(
        module,
        "_cleanup_delivered_worktrees",
        lambda target, source, members: ([str(source)], []),
    )

    target_heads = iter(("base", "expected"))

    def fake_git(repository: Path, *arguments: str, **kwargs: object) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return "expected" if repository == source else next(target_heads)
        if arguments[0] in {"merge", "push"}:
            return ""
        raise AssertionError(arguments)

    monkeypatch.setattr(module, "_git", fake_git)

    result = module.batch_deliver(source, target, "base", "expected")

    assert result["status"] == "delivered"
    assert result["remote"] == "expected"
    assert result["plans"] == ["changes/example/plans/example.md"]
    assert result["validation"]["source"] == "expected"


def test_manifest_gate_preserves_declared_command_order(tmp_path: Path) -> None:
    module = _load_module()
    manifest = module.load_manifest(Path(__file__).resolve().parents[1] / "signetum.toml")
    graph, _ = module._runtime_validation(manifest)
    shards = {shard.name: shard.command for shard in graph.shards}
    commands = [shards[name] for name in graph.gate("member").shards]
    assert set(commands) == {
        ("uv", "sync", "--locked", "--all-extras", "--dev"),
        ("uv", "build"),
        ("uv", "run", "pre-commit", "run", "--all-files"),
        ("uv", "run", "--no-sync", "ruff", "check", "."),
        ("uv", "run", "--no-sync", "ruff", "format", "--check", "."),
        ("uv", "run", "--no-sync", "bandit", "-r", "src"),
        ("uv", "run", "pytest"),
    }


def test_delivery_provenance_reads_named_member_and_plan_trailer(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_module()
    responses = {
        ("rev-list", "--reverse", "--first-parent", "--merges", "base..tip"): "merge-1",
        ("show", "-s", "--format=%P", "merge-1"): "base member-tip",
        ("show", "-s", "--format=%s", "merge-1"): "merge: admit impl/member",
        ("show", "-s", "--format=%s", "member-tip"): "feat: deliver member",
        ("show", "-s", "--format=%B", "merge-1"): (
            "merge: admit impl/member\n\n"
            "Signetum-Original: member-tip\n"
            "Signetum-Patch-ID: stable-patch\n"
            "Signetum-Ready-Evidence: member-ready.json\n"
            "Signetum-Plan: changes/example/plans/member.md\n"
        ),
    }
    monkeypatch.setattr(
        module,
        "_git",
        lambda repository, *arguments, **kwargs: responses[arguments],
    )

    members, plans = module._delivery_provenance(tmp_path, "base", "tip")

    assert members == [
        {
            "branch": "impl/member",
            "original": "member-tip",
            "patch_id": "stable-patch",
            "ready_evidence": "member-ready.json",
            "plan": "changes/example/plans/member.md",
            "admission_commit": "merge-1",
            "summary": "feat: deliver member",
        }
    ]
    assert plans == ["changes/example/plans/member.md"]


def test_admission_records_ready_patch_plan_and_deterministically_numbers_proposals(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "repository")
    base = _git(repository, "rev-parse", "HEAD")
    member = tmp_path / "member"
    batch = tmp_path / "batch"
    _git(repository, "worktree", "add", "-b", "impl/member", str(member), base)
    _git(repository, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(member, "impl/member", base)
    _record(batch, "batch/test", base, "batch")
    decision = member / "docs/decisions/ADP-zebra.md"
    decision.parent.mkdir(parents=True)
    decision.write_text(
        "# Zebra\n\nStatus: Proposed\nSupersedes: ADP-yak.md\nSuperseded by: None\n"
        "\nSee ADP-zebra.md.\n",
        encoding="utf-8",
    )
    (member / "docs/decisions/ADP-yak.md").write_text(
        "# Yak\n\nStatus: Accepted\nSupersedes: None\nSuperseded by: None\n",
        encoding="utf-8",
    )
    plan = "changes/example/plans/member.md"
    (member / "reference.md").write_text(
        "Decision: docs/decisions/ADP-zebra.md\n", encoding="utf-8"
    )
    _git(member, "add", ".")
    _git(member, "commit", "-m", f"deliver member\n\nDelivers: {plan}")
    member_tip = _git(member, "rev-parse", "HEAD")
    _evidence_receipt(
        member,
        "member-lifecycle-ready.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )

    result = lifecycle.admit(batch, (member,))

    formal = batch / "docs/decisions/ADP-0001-zebra.md"
    assert result["status"] == "admitted"
    assert formal.is_file()
    assert not (batch / "docs/decisions/ADP-zebra.md").exists()
    assert "Status: Accepted" in formal.read_text(encoding="utf-8")
    # Numbering records the supersession on the replaced decision too, so no
    # reader of it is left believing it still stands.
    assert "Superseded by: ADP-0001-zebra.md" in (batch / "docs/decisions/ADP-yak.md").read_text(
        encoding="utf-8"
    )
    assert "ADP-0001-zebra.md" in formal.read_text(encoding="utf-8")
    assert "ADP-0001-zebra.md" in (batch / "reference.md").read_text(encoding="utf-8")
    admitted_members = result["admitted"]
    assert isinstance(admitted_members, list)
    admitted = admitted_members[0]
    assert admitted["branch"] == "impl/member"
    assert admitted["original"] == member_tip
    assert admitted["ready_evidence"] == "member-lifecycle-ready.json"
    assert admitted["plan"] == [plan]
    assert admitted["patch_id"]
    assert admitted["admission_commit"]
    assert result["decisions"] == [
        {
            "proposal": "docs/decisions/ADP-zebra.md",
            "formal": "docs/decisions/ADP-0001-zebra.md",
        }
    ]
    repeated = lifecycle.admit(batch, (member,))
    assert repeated["admitted"] == []
    unchanged_members = repeated["unchanged"]
    assert isinstance(unchanged_members, list)
    assert unchanged_members[0]["original"] == member_tip

    (member / "incremental.txt").write_text("second admission\n", encoding="utf-8")
    _git(member, "add", ".")
    _git(member, "commit", "-m", f"extend member\n\nDelivers: {plan}")
    advanced_tip = _git(member, "rev-parse", "HEAD")
    _evidence_receipt(
        member,
        "member-lifecycle-advanced.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )
    incremental = lifecycle.admit(batch, (member,))
    incremental_members = incremental["admitted"]
    assert isinstance(incremental_members, list)
    assert incremental_members[0]["original"] == advanced_tip
    assert incremental_members[0]["admission_commit"] != admitted["admission_commit"]


def test_delivery_refuses_numbering_bound_to_another_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    monkeypatch.setattr(lifecycle, "_require_clean", lambda path: None)
    monkeypatch.setattr(lifecycle, "_recorded_base", lambda path, branch=None: "older-base")
    monkeypatch.setattr(
        lifecycle,
        "_git",
        lambda repository, *arguments, **kwargs: "tip" if repository == source else "approved-base",
    )

    with pytest.raises(lifecycle.AdmissionError, match="recorded batch base differs"):
        lifecycle.batch_deliver(source, target, "approved-base", "tip")


def test_final_refuses_proposal_decisions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository")
    proposal = repository / "docs/decisions/ADP-unresolved.md"
    proposal.parent.mkdir(parents=True)
    proposal.write_text("# unresolved\n\nStatus: Proposed\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "add proposal")
    _record(repository, "main", _git(repository, "rev-parse", "HEAD"), "batch")
    with pytest.raises(lifecycle.AdmissionError, match="proposal decision"):
        lifecycle.validate(repository, "final")


def _member_and_batch(tmp_path: Path, *, path: str = "src/feature.txt") -> tuple[Path, Path, str]:
    repository = _repository(tmp_path / "repository")
    base = _git(repository, "rev-parse", "HEAD")
    member = tmp_path / "member"
    batch = tmp_path / "batch"
    _git(repository, "worktree", "add", "-b", "impl/member", str(member), base)
    _git(repository, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(member, "impl/member", base)
    _record(batch, "batch/test", base, "batch")
    target = member / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("work\n", encoding="utf-8")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "deliver member\n\nDelivers: changes/example/plans/member.md")
    return member, batch, base


def test_a_completed_final_gate_satisfies_member_admission(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path)
    _evidence_receipt(
        member,
        "final-lifecycle-frozen.json",
        gate="final",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND, ("extra",)),
    )

    result = lifecycle.admit(batch, (member,))

    admitted = result["admitted"]
    assert isinstance(admitted, list)
    assert admitted[0]["ready_evidence"] == "final-lifecycle-frozen.json"


def test_evidence_survives_a_commit_which_did_not_change_the_tree(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path)
    tree = _git(member, "rev-parse", "HEAD^{tree}")
    _evidence_receipt(
        member,
        "member-lifecycle-ready.json",
        gate="member",
        tree=tree,
        commands=(MEMBER_COMMAND,),
    )
    original = _git(member, "rev-parse", "HEAD")
    _git(member, "commit", "--amend", "-m", "reworded\n\nDelivers: changes/example/plans/member.md")
    amended = _git(member, "rev-parse", "HEAD")

    assert amended != original
    assert _git(member, "rev-parse", "HEAD^{tree}") == tree

    result = lifecycle.admit(batch, (member,))

    admitted = result["admitted"]
    assert isinstance(admitted, list)
    assert admitted[0]["original"] == amended
    assert admitted[0]["ready_evidence"] == "member-lifecycle-ready.json"


def test_evidence_proving_the_wrong_commands_is_not_admission(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path)
    _evidence_receipt(
        member,
        "member-lifecycle-unrelated.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(("something", "else"),),
    )

    with pytest.raises(lifecycle.AdmissionError, match="no evidence proving its selected"):
        lifecycle.admit(batch, (member,))


def test_a_member_whose_authority_is_final_records_a_deferred_closure(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path, path="docs/note.md")

    result = lifecycle.admit(batch, (member,))

    admitted = result["admitted"]
    assert isinstance(admitted, list)
    assert admitted[0]["ready_evidence"].startswith("deferred:requires-final:")
    assert "governance" in admitted[0]["ready_evidence"]


def test_a_failing_gate_is_refused_as_one_json_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failing gate is an ordinary outcome, never an unhandled traceback."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise lifecycle.ValidationExecutionError("validation shard failed: engine:ruff")

    monkeypatch.setattr(lifecycle, "validate", refuse)

    assert lifecycle.main(["final"]) == 2


def _without_change_packages(worktree: Path) -> None:
    """Leave a tree whose declared specification authority matches nothing."""

    for path in worktree.glob("changes/*/specs/*.toml"):
        path.unlink()


def test_a_tree_hosting_no_change_admits_a_member_without_a_plan(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path)
    _without_change_packages(member)
    _git(member, "commit", "-a", "--allow-empty", "-m", "render without a change package")
    _evidence_receipt(
        member,
        "member-lifecycle-ready.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )

    result = lifecycle.admit(batch, (member,))

    admitted = result["admitted"]
    assert isinstance(admitted, list)
    assert admitted[0]["plan"] == []


def test_a_tree_hosting_a_change_still_requires_a_plan(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository")
    base = _git(repository, "rev-parse", "HEAD")
    member = tmp_path / "member"
    batch = tmp_path / "batch"
    _git(repository, "worktree", "add", "-b", "impl/member", str(member), base)
    _git(repository, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(member, "impl/member", base)
    _record(batch, "batch/test", base, "batch")
    specification = member / "changes/example/specs/first.toml"
    specification.parent.mkdir(parents=True)
    specification.write_text("[specification]\n", encoding="utf-8")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "record a change package without naming it")

    with pytest.raises(lifecycle.AdmissionError, match="no Delivers Plan trailer"):
        lifecycle.admit(batch, (member,))


def test_a_named_plan_outside_a_change_is_still_refused(tmp_path: Path) -> None:
    assert lifecycle._change_ids_from_plans(("changes/one/plans/a.md",)) == ("one",)

    with pytest.raises(lifecycle.AdmissionError, match="outside one active Change"):
        lifecycle._change_ids_from_plans(("unified-repository-configuration",))
