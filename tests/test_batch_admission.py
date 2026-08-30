"""Behavior tests for the bootstrap batch-admission authority."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import reposeal.lifecycle as lifecycle


def _load_module():
    return lifecycle


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(  # nosec B603
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "RepoSeal Tests")
    _git(path, "config", "user.email", "reposeal@example.invalid")
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "seed")
    return path


def test_delivery_branch_names_are_refused() -> None:
    module = _load_module()

    assert {"main", "master", "product"}.isdisjoint({"batch/reposeal-v2"})
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
    monkeypatch.setattr(module, "_batch_base", lambda path, tip: "base")
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


def test_gate_builds_release_inputs_before_running_repository_checks(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_module()
    commands: list[tuple[str, ...]] = []

    class Completed:
        returncode = 0

    def record(command: tuple[str, ...], **kwargs: object) -> Completed:
        commands.append(command)
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", record)

    module._run_gate(tmp_path)

    assert commands == [
        ("uv", "build"),
        ("uv", "run", "pre-commit", "run", "--all-files"),
        ("uv", "run", "--no-sync", "ruff", "check", "."),
        ("uv", "run", "--no-sync", "ruff", "format", "--check", "."),
        ("uv", "run", "--no-sync", "bandit", "-r", "src"),
        ("uv", "run", "--no-sync", "pip-audit"),
    ]


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
            "RepoSeal-Original: member-tip\n"
            "RepoSeal-Patch-ID: stable-patch\n"
            "RepoSeal-Ready-Evidence: member-ready.json\n"
            "RepoSeal-Plan: changes/example/plans/member.md\n"
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
    decision = member / "docs/decisions/ADP-proposal-zebra.md"
    decision.parent.mkdir(parents=True)
    decision.write_text("# Zebra\n\nSee ADP-proposal-zebra.md.\n", encoding="utf-8")
    plan = "changes/example/plans/member.md"
    (member / "reference.md").write_text(
        "Decision: docs/decisions/ADP-proposal-zebra.md\n", encoding="utf-8"
    )
    _git(member, "add", ".")
    _git(member, "commit", "-m", f"deliver member\n\nDelivers: {plan}")
    member_tip = _git(member, "rev-parse", "HEAD")
    receipts = lifecycle._receipt_root(member)
    ready = receipts / "member-ready.json"
    ready.write_text(
        json.dumps({"kind": "member", "source": member_tip, "base": base, "valid": True}),
        encoding="utf-8",
    )

    result = lifecycle.admit(batch, (member,))

    formal = batch / "docs/decisions/ADP-0001-zebra.md"
    assert result["status"] == "admitted"
    assert formal.is_file()
    assert not (batch / "docs/decisions/ADP-proposal-zebra.md").exists()
    assert "ADP-0001-zebra.md" in formal.read_text(encoding="utf-8")
    assert "ADP-0001-zebra.md" in (batch / "reference.md").read_text(encoding="utf-8")
    admitted_members = result["admitted"]
    assert isinstance(admitted_members, list)
    admitted = admitted_members[0]
    assert admitted["branch"] == "impl/member"
    assert admitted["original"] == member_tip
    assert admitted["ready_evidence"] == "member-ready.json"
    assert admitted["plan"] == [plan]
    assert admitted["patch_id"]
    assert admitted["admission_commit"]
    assert result["decisions"] == [
        {
            "proposal": "docs/decisions/ADP-proposal-zebra.md",
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
    (receipts / "member-advanced.json").write_text(
        json.dumps({"kind": "member", "source": advanced_tip, "base": base, "valid": True}),
        encoding="utf-8",
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
    monkeypatch.setattr(lifecycle, "_batch_base", lambda path, tip: "older-base")
    monkeypatch.setattr(
        lifecycle,
        "_git",
        lambda repository, *arguments, **kwargs: "tip" if repository == source else "approved-base",
    )

    with pytest.raises(lifecycle.AdmissionError, match="expected base"):
        lifecycle.batch_deliver(source, target, "approved-base", "tip")


def test_final_refuses_proposal_decisions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository")
    proposal = repository / "docs/decisions/ADP-proposal-unresolved.md"
    proposal.parent.mkdir(parents=True)
    proposal.write_text("# unresolved\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "add proposal")
    monkeypatch.setattr(lifecycle, "_run_gate", lambda path: None)

    with pytest.raises(lifecycle.AdmissionError, match="proposal decision"):
        lifecycle.validate(repository, None, "final")
