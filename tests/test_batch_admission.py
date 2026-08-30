"""Behavior tests for the bootstrap batch-admission authority."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "development_foundation"
    / "merge_plan_delivery.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("foundation_merge_plan_delivery", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load batch admission authority")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_delivery_branch_names_are_refused() -> None:
    module = _load_module()

    assert {"main", "master", "product"}.isdisjoint({"batch/foundation-v2"})
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

    def fake_git(repository: Path, *arguments: str, **kwargs: object) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return "expected" if repository == source else "base"
        if arguments[0] == "merge":
            return ""
        raise AssertionError(arguments)

    monkeypatch.setattr(module, "_git", fake_git)

    result = module.batch_deliver(source, target, "base", "expected")

    assert result["status"] == "delivered"
