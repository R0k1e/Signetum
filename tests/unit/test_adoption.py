"""Adoption writes exact bindings and preserves a project's own entrypoints."""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
import signetum.adoption as owner
from signetum.adoption import AdoptionRequest, Retirement, apply, plan_digest, preview
from signetum.git import git_output
from signetum.runtime_identity import implementation_digest


@pytest.fixture
def adoption(local_repository):
    root, _ = local_repository
    (root / "CLAUDE.md").write_text("Project-owned instructions.\n")
    (root / "AGENTS.md").symlink_to("CLAUDE.md")
    (root / "Justfile").write_text("test:\n    existing-test\n")
    manifest = (
        (root / "signetum.toml")
        .read_text()
        .replace("[signetum]", '[signetum]\nengine_digest = "' + implementation_digest() + '"')
    )
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "existing application")
    return root, AdoptionRequest(manifest=manifest)


def test_review_apply_and_exact_retry_preserve_application_and_unrelated_work(adoption):
    root, request = adoption
    (root / "user-work").write_text("unrelated")
    before = {p: p.read_bytes() for p in (root / "CLAUDE.md", root / "Justfile")}
    status = git_output(root, "status", "--porcelain")
    proposal = preview(root, request)
    assert {f.path for f in proposal.files} == {"signetum.toml"}
    assert git_output(root, "status", "--porcelain") == status
    assert apply(root, proposal, plan_digest(proposal))["status"] == "applied"
    assert apply(root, proposal, plan_digest(proposal))["status"] == "unchanged"
    assert (root / "AGENTS.md").is_symlink()
    assert all(p.read_bytes() == content for p, content in before.items())
    assert (root / "user-work").read_text() == "unrelated"


@pytest.mark.parametrize("changed", ["digest", "source", "target", "payload", "symlink"])
def test_stale_or_unsafe_adoption_refuses_before_any_write(adoption, tmp_path, changed):
    root, request = adoption
    proposal = preview(root, request)
    expected = plan_digest(proposal)
    if changed == "digest":
        expected = "sha256:" + "0" * 64
    elif changed == "source":
        git_output(root, "commit", "--allow-empty", "-m", "new source")
    elif changed == "target":
        (root / "signetum.toml").write_text("new user bindings")
    elif changed == "payload":
        proposal = replace(proposal, files=(replace(proposal.files[0], after="unreviewed"),))
        expected = plan_digest(proposal)
    else:
        target = root / "signetum.toml"
        target.unlink()
        target.symlink_to(tmp_path / "outside")
    status = git_output(root, "status", "--porcelain")
    with pytest.raises(ValueError):
        apply(root, proposal, expected)
    assert git_output(root, "status", "--porcelain") == status


def test_partial_filesystem_failure_rolls_back_owned_writes(adoption, monkeypatch):
    root, request = adoption
    proposal = preview(root, request)
    before = (root / "signetum.toml").read_bytes()

    def fail(path: Path, text: str):
        raise OSError("injected disk failure")

    monkeypatch.setattr(owner, "_replace", fail)
    with pytest.raises(OSError, match="disk failure"):
        apply(root, proposal, plan_digest(proposal))
    assert (root / "signetum.toml").read_bytes() == before


def test_invalid_bindings_and_subdirectory_do_not_create_a_plan(adoption):
    root, request = adoption
    with pytest.raises(ValueError):
        preview(root, replace(request, manifest="not toml"))
    directory = root / "subdir"
    directory.mkdir()
    with pytest.raises(ValueError, match="repository root"):
        preview(directory, request)


def test_exact_managed_retirement_preserves_changed_and_unmanaged_files(adoption):
    root, request = adoption
    directory = root / ".agents/signetum/runtime/_signetum_runtime"
    directory.mkdir(parents=True)
    content = b"owned=True\n"
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    (directory / "owned.py").write_bytes(content)
    (directory / "runtime.toml").write_text('[files]\n"owned.py"="' + digest + '"\n')
    (directory / "custom.py").write_text("user_owned=True\n")
    request = replace(
        request,
        retirements=(
            Retirement(path=(directory / "owned.py").relative_to(root).as_posix(), digest=digest),
        ),
    )
    proposal = preview(root, request)
    (directory / "owned.py").write_text("user change")
    with pytest.raises(ValueError):
        apply(root, proposal, plan_digest(proposal))
    (directory / "owned.py").write_bytes(content)
    assert apply(root, proposal, plan_digest(proposal))["status"] == "applied"
    assert (directory / "custom.py").read_text() == "user_owned=True\n"
    assert apply(root, proposal, plan_digest(proposal))["status"] == "unchanged"
