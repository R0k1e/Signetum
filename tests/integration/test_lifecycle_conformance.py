from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from signetum import lifecycle as engine_lifecycle

ROOT = Path(__file__).resolve().parents[2]


def _template_lifecycle() -> ModuleType:
    path = ROOT / "template" / ".agents" / "repo-dev" / "runtime" / "lifecycle.py"
    spec = importlib.util.spec_from_file_location("template_lifecycle", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git_for(files: tuple[str, ...]):
    def fake_git(repository: Path, *arguments: str, check: bool = True) -> str:
        del repository, check
        if arguments[:2] == ("diff", "--name-only"):
            return "\n".join(files)
        if arguments == ("rev-parse", "HEAD"):
            return "a" * 40
        raise AssertionError(arguments)

    return fake_git


@pytest.mark.parametrize("runtime", (engine_lifecycle, _template_lifecycle()))
def test_changed_contract_vectors_are_shared(
    runtime: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "signetum.toml").write_text(
        (ROOT / "template" / "signetum.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    vectors = json.loads(
        (ROOT / "tests" / "fixtures" / "lifecycle-impact-vectors.json").read_text(encoding="utf-8")
    )["cases"]
    for vector in vectors:
        monkeypatch.setattr(runtime, "_git", _git_for(tuple(vector["files"])))
        monkeypatch.setattr(runtime, "_recorded_base", lambda repository, branch=None: "base")
        observed = runtime.changed(tmp_path, True)
        for field in (
            "rules",
            "profiles",
            "gates",
            "shards",
            "unexplained",
            "requires_final",
        ):
            value = observed[field]
            assert (
                list(value) == vector[field]
                if isinstance(value, (list, tuple))
                else value == vector[field]
            )


@pytest.mark.parametrize("runtime", (engine_lifecycle, _template_lifecycle()))
def test_local_validation_state_has_one_git_common_root(
    runtime: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    common = tmp_path / "common"
    monkeypatch.setattr(runtime, "_git", lambda *args, **kwargs: str(common))

    assert runtime._receipt_root(tmp_path) == common / "signetum" / "validation"
