"""Adoption changes only reviewed files and never treats installation as approval."""

from dataclasses import replace
from pathlib import Path

import pytest

import signetum.adoption as owner
from signetum.adoption import AdoptionRequest, apply, plan_digest, preview
from signetum.git import git_output


@pytest.fixture
def adoption(local_repository):
    root, _ = local_repository
    architecture = root / "docs/ARCHITECTURE.md"
    architecture.parent.mkdir()
    architecture.write_text("# Existing architecture\n")
    (root / "AGENTS.md").write_text("Existing instructions.\n")
    (root / "Justfile").write_text("test:\n    existing-test\n")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "existing application")
    request = AdoptionRequest(
        manifest=(root / "signetum.toml").read_text(),
        policy=(root / ".agents/signetum/repo.yaml").read_text(),
    )
    return root, request


def test_review_apply_and_exact_retry_preserve_application_and_unrelated_work(adoption):
    root, request = adoption
    (root / "user-work").write_text("not part of adoption")
    before = (root / "Justfile").read_bytes()
    status = git_output(root, "status", "--porcelain")
    plan = preview(root, request)
    assert git_output(root, "status", "--porcelain") == status
    assert apply(root, plan, plan_digest(plan))["status"] == "applied"
    assert (root / "Justfile").read_bytes() == before
    assert (root / "user-work").read_text() == "not part of adoption"
    assert (root / "AGENTS.md").read_text().startswith("Existing instructions.\n")
    assert apply(root, plan, plan_digest(plan))["status"] == "unchanged"
    assert (root / ".agents/signetum/runtime/protocol.py").is_file()


@pytest.mark.parametrize("changed", ["digest", "source", "target", "payload", "symlink"])
def test_stale_or_unsafe_adoption_refuses_before_any_write(adoption, tmp_path, changed):
    root, request = adoption
    plan = preview(root, request)
    expected = plan_digest(plan)
    if changed == "digest":
        expected = "sha256:" + "0" * 64
    elif changed == "source":
        git_output(root, "commit", "--allow-empty", "-m", "new source")
    elif changed == "target":
        (root / "AGENTS.md").write_text("new user instructions")
    elif changed == "payload":
        item = replace(plan.files[0], after="unreviewed")
        plan = replace(plan, files=(item, *plan.files[1:]))
        expected = plan_digest(plan)
    else:
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / ".agents/signetum/runtime").symlink_to(outside, target_is_directory=True)
    status = git_output(root, "status", "--porcelain")
    with pytest.raises(ValueError):
        apply(root, plan, expected)
    assert git_output(root, "status", "--porcelain") == status
    assert not (root / ".agents/signetum/run").exists()


def test_partial_filesystem_failure_rolls_back_owned_writes(adoption, monkeypatch):
    root, request = adoption
    plan = preview(root, request)
    original = owner._replace
    calls = 0

    def fail(path: Path, text: str):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected disk failure")
        original(path, text)

    monkeypatch.setattr(owner, "_replace", fail)
    before = git_output(root, "status", "--porcelain")
    with pytest.raises(OSError, match="disk failure"):
        apply(root, plan, plan_digest(plan))
    assert git_output(root, "status", "--porcelain") == before


@pytest.mark.parametrize(
    "field,value", [("manifest", "not toml"), ("policy", "{}"), ("interpreter", ())]
)
def test_invalid_bindings_do_not_create_a_plan(adoption, field, value):
    root, request = adoption
    before = git_output(root, "status", "--porcelain")
    with pytest.raises(ValueError):
        preview(root, replace(request, **{field: value}))
    assert git_output(root, "status", "--porcelain") == before


def test_subdirectory_and_unmanaged_runtime_are_explicit_refusals(adoption):
    root, request = adoption
    with pytest.raises(ValueError, match="repository root"):
        preview(root / "docs", request)
    unmanaged = root / ".agents/signetum/runtime/_signetum_runtime/custom.py"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text("user_owned = True\n")
    with pytest.raises(ValueError, match="unmanaged runtime"):
        preview(root, request)
    assert unmanaged.read_text() == "user_owned = True\n"
