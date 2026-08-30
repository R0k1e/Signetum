"""Behavior tests for the bootstrap batch-admission authority."""

from __future__ import annotations

import importlib.util
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
def test_ancestor_query_has_two_valid_outcomes(monkeypatch, tmp_path: Path, return_code: int) -> None:
    module = _load_module()

    class Completed:
        stderr = ""

        def __init__(self, code: int) -> None:
            self.returncode = code

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: Completed(return_code))

    assert module._is_ancestor(tmp_path, "member", "batch") is (return_code == 0)
