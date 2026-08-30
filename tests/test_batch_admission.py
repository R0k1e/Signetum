"""Behavior tests for the bootstrap batch-admission authority."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import reposeal.lifecycle as lifecycle


def _load_module():
    return lifecycle


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
        json.dumps({"source": "expected", "valid": True}), encoding="utf-8"
    )

    monkeypatch.setattr(module, "_require_clean", lambda path: None)
    monkeypatch.setattr(module, "_receipt_root", lambda path: receipts)
    monkeypatch.setattr(module, "_branch", lambda path: "main")
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

    assert [command[3:] for command in commands] == [
        ("uv", "build"),
        ("uv", "run", "pre-commit", "run", "--all-files"),
        ("uv", "run", "--no-sync", "ruff", "check", "."),
        ("uv", "run", "--no-sync", "ruff", "format", "--check", "."),
        ("uv", "run", "--no-sync", "bandit", "-r", "src"),
        ("uv", "run", "--no-sync", "pip-audit"),
    ]
    assert all(command[1:3] == ("exec", "--") for command in commands)


def test_delivery_provenance_reads_named_member_and_plan_trailer(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_module()
    responses = {
        ("rev-list", "--reverse", "--first-parent", "--merges", "base..tip"): "merge-1",
        ("show", "-s", "--format=%P", "merge-1"): "base member-tip",
        ("show", "-s", "--format=%s", "merge-1"): "merge: admit impl/member",
        ("show", "-s", "--format=%s", "member-tip"): "feat: deliver member",
        ("show", "-s", "--format=%B", "member-tip"): (
            "feat: deliver member\n\nDelivers: changes/example/plans/member.md\n"
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
            "integrated": "merge-1",
            "summary": "feat: deliver member",
        }
    ]
    assert plans == ["changes/example/plans/member.md"]
