"""Adoption writes exact bindings and preserves a project's own entrypoints."""

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
import signetum.adoption as owner
from signetum.adoption import AdoptionRequest, Retirement, apply, plan_digest, preview
from signetum.git import git_output


@pytest.fixture
def adoption(local_repository):
    root, _ = local_repository
    (root / "CLAUDE.md").write_text("Project-owned instructions.\n")
    (root / "AGENTS.md").symlink_to("CLAUDE.md")
    (root / "Justfile").write_text("test:\n    existing-test\n")
    manifest = (root / "signetum.toml").read_text()
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "existing application")
    return root, AdoptionRequest(manifest=manifest + "\n# Reviewed adoption bindings.\n")


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
    retired = root / ".agents/signetum/run"
    retired.parent.mkdir(parents=True, exist_ok=True)
    retired.write_text("#!/bin/sh\nexit 0\n")
    retired.chmod(0o755)
    digest = "sha256:" + hashlib.sha256(retired.read_bytes()).hexdigest()
    request = replace(
        request, retirements=(Retirement(path=".agents/signetum/run", digest=digest),)
    )
    proposal = preview(root, request)
    before = (root / "signetum.toml").read_bytes()
    original = owner._replace
    calls = 0

    def fail_once(path: Path, text: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected disk failure")
        original(path, text)

    monkeypatch.setattr(owner, "_replace", fail_once)
    with pytest.raises(OSError, match="disk failure"):
        apply(root, proposal, plan_digest(proposal))
    assert (root / "signetum.toml").read_bytes() == before
    assert retired.read_text() == "#!/bin/sh\nexit 0\n"
    assert retired.stat().st_mode & 0o777 == 0o755


def test_invalid_bindings_and_subdirectory_do_not_create_a_plan(adoption):
    root, request = adoption
    with pytest.raises(ValueError):
        preview(root, replace(request, manifest="not toml"))
    invalid = (
        request.manifest.replace('[delivery]\nbranch = "main"\n', ""),
        request.manifest.replace('shards = ["test:check"]', "shards = []"),
        request.manifest.replace("protocol = 2", "protocol = 99"),
        request.manifest.replace(
            "[signetum]", '[signetum]\nengine_digest = "sha256:' + "0" * 64 + '"'
        ),
    )
    before = git_output(root, "status", "--porcelain")
    for manifest in invalid:
        with pytest.raises(ValueError):
            preview(root, replace(request, manifest=manifest))
    assert git_output(root, "status", "--porcelain") == before
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
    custom = directory / "custom.py"
    unknown = Retirement(
        path=custom.relative_to(root).as_posix(),
        digest="sha256:" + hashlib.sha256(custom.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="inventoried"):
        preview(root, replace(request, retirements=(unknown,)))
    with pytest.raises(ValueError, match="inventoried"):
        preview(root, replace(request, retirements=request.retirements * 2))
    proposal = preview(root, request)
    (directory / "owned.py").write_text("user change")
    with pytest.raises(ValueError):
        apply(root, proposal, plan_digest(proposal))
    (directory / "owned.py").write_bytes(content)
    assert apply(root, proposal, plan_digest(proposal))["status"] == "applied"
    assert (directory / "custom.py").read_text() == "user_owned=True\n"
    assert apply(root, proposal, plan_digest(proposal))["status"] == "unchanged"


def test_inspect_reports_versions_and_keeps_a_low_git_floor_inspected(adoption, monkeypatch):
    root, _request = adoption

    real_run = subprocess.run

    def which(name):
        return f"/usr/bin/{name}"

    def run(argv, **kwargs):
        arguments = tuple(argv)
        if arguments[1:3] == ("exec", "--"):
            text = "uv 0.12.2\n"
        elif arguments[-1:] == ("--version",) and Path(arguments[0]).name == "git":
            text = "git version 2.6.0 (Fixture)\n"
        elif arguments[-1:] == ("--version",):
            text = f"{Path(arguments[0]).name} 1.0.0\n"
        else:
            return real_run(argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, text, "")

    monkeypatch.setattr(owner, "which", which)
    monkeypatch.setattr(owner.subprocess, "run", run)
    report = owner.inspect(root)
    git_report = report["tools"]["git"]
    assert report["status"] == "inspected"
    assert isinstance(git_report, dict)
    assert git_report["present"] is True
    assert git_report["version"] == "git version 2.6.0 (Fixture)"
    floors = git_report["floors"]
    assert isinstance(floors, dict)
    assert floors["signetum_commands"]["met"] is False
    assert floors["worktrunk_cleanup"]["minimum"] == "2.17"
    assert floors["worktrunk_cleanup"]["met"] is False
    assert report["uv_resolution"] == {
        "path": "uv 1.0.0",
        "mise": "uv 0.12.2",
        "differs": True,
    }


def test_inspect_reports_a_missing_tool_without_failing(adoption, monkeypatch):
    root, _request = adoption
    monkeypatch.setattr(owner, "which", lambda name: None)
    report = owner.inspect(root)
    assert report["status"] == "inspected"
    assert report["tools"]["git"] == {
        "present": False,
        "version": None,
        "floors": {
            "signetum_commands": {"minimum": "2.7", "met": False},
            "worktrunk_cleanup": {"minimum": "2.17", "met": False},
        },
    }
    assert report["uv_resolution"] == {"path": None, "mise": None, "differs": False}


def test_second_preview_leaves_the_existing_file_unchanged(adoption, tmp_path, capsys):
    root, request = adoption
    request_path = tmp_path / "request.json"
    output = tmp_path / "plan.json"
    request_path.write_text(json.dumps({"manifest": request.manifest}))
    arguments = [
        "preview",
        "--repository",
        str(root),
        "--request",
        str(request_path),
        "--output",
        str(output),
    ]
    assert owner.main(arguments) == 0
    first = output.read_bytes()
    assert owner.main(arguments) != 0
    captured = capsys.readouterr()
    assert "preview file already exists" in captured.out
    assert "choose another --output" in captured.out
    assert "Errno" not in captured.out
    assert "File exists" not in captured.out
    assert output.read_bytes() == first
