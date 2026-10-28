"""Observable changed behavior against both native repository frontends."""

import json
import sys
from pathlib import Path

import pytest
from test_lifecycle_conformance import _template_lifecycle

from signetum import lifecycle
from signetum.git import git_output
from signetum.workspaces import WorkspaceRecord, state_root, write_record


@pytest.fixture(params=["engine", "template"])
def diagnostic(request, repository, monkeypatch, tmp_path):
    root, state = repository
    runtime = lifecycle if request.param == "engine" else _template_lifecycle()

    def open_member(*, code=None, selected=True, world=False):
        manifest = root / "signetum.toml"
        text = manifest.read_text()
        if code is not None:
            text = text.replace('["true"]', json.dumps([sys.executable, "-c", code]))
        if not selected:
            text = text.replace('paths = ["**"]', 'paths = ["src/**"]')
        if world:
            text = text.replace('shards = ["test:check"]', 'shards = ["test:world"]', 1)
            text += (
                '\n[[validation.shards]]\nname = "test:world"\nevidence = "world"\n'
                'command = ["false"]\n'
            )
        manifest.write_text(text)
        git_output(root, "add", ".")
        git_output(root, "commit", "--allow-empty", "-m", "declare diagnostic fixture")
        base = git_output(root, "rev-parse", "HEAD")
        member = tmp_path / "member"
        branch = "plan/native-diagnostic"
        git_output(root, "worktree", "add", "-b", branch, str(member), base)
        write_record(state_root(root), WorkspaceRecord(1, branch, base, "member"))
        return member

    return runtime, open_member, state


def commit_contribution(member):
    (member / "implementation.txt").write_text("committed contribution\n")
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "implement contribution")
    return git_output(member, "rev-parse", "HEAD")


@pytest.mark.parametrize("fails", [False, True])
def test_changed_executes_selected_command_without_readiness(diagnostic, fails):
    runtime, open_member, state = diagnostic
    marker = state / "executed"
    code = (
        "from pathlib import Path; import sys; "
        f"Path({str(marker)!r}).touch(); sys.exit({int(fails)})"
    )
    member = open_member(code=code)
    tip = commit_contribution(member)
    if fails:
        with pytest.raises(runtime.ValidationExecutionError, match="exited 1"):
            runtime.changed(member, True)
    else:
        result = runtime.changed(member, True)
        assert result["executed"] == ["test:check"]
        assert result["checks_started"] is True
    assert marker.exists()
    assert git_output(member, "rev-parse", "HEAD") == tip
    assert not (state_root(member) / "validation").exists()


def test_changed_selection_only_is_explicit_and_does_not_execute(diagnostic):
    runtime, open_member, state = diagnostic
    marker = state / "must-not-execute"
    member = open_member(code=f"from pathlib import Path; Path({str(marker)!r}).touch()")
    commit_contribution(member)
    result = runtime.changed(member, True, validate_only=True)
    assert result["status"] == "selection-only"
    assert result["executed"] == []
    assert result["checks_started"] is False
    assert not marker.exists()
    assert not (state_root(member) / "validation").exists()


@pytest.mark.parametrize("dirty", [False, True])
def test_changed_requires_a_clean_committed_contribution(diagnostic, dirty):
    runtime, open_member, _ = diagnostic
    member = open_member()
    if dirty:
        commit_contribution(member)
        (member / "untracked.txt").write_text("retained state")
    with pytest.raises(runtime.AdmissionError, match="not clean" if dirty else "no committed"):
        runtime.changed(member, True)
    assert not (state_root(member) / "validation").exists()


def test_changed_does_not_expand_to_required_member_checks_when_unselected(diagnostic):
    runtime, open_member, _ = diagnostic
    member = open_member(code="raise SystemExit(7)", selected=False)
    commit_contribution(member)
    result = runtime.changed(member, True)
    assert result["status"] == "nothing-selected"
    assert result["executed"] == []
    assert result["requires_final"] is True


def test_changed_defers_world_checks_without_running_member_required_checks(diagnostic):
    runtime, open_member, _ = diagnostic
    member = open_member(code="raise SystemExit(7)", world=True)
    commit_contribution(member)
    result = runtime.changed(member, True)
    assert result["executed"] == []
    assert result["deferred_world_shards"] == ("test:world",)


def test_changed_refuses_success_after_a_check_mutates_working_files(diagnostic):
    runtime, open_member, _ = diagnostic
    member = open_member(code="from pathlib import Path; Path('seed.txt').write_text('changed')")
    commit_contribution(member)
    with pytest.raises(runtime.ValidationExecutionError, match="diagnostic changed working files"):
        runtime.changed(member, True)
    assert (member / "seed.txt").read_text() == "changed"
    assert not (state_root(member) / "validation").exists()


@pytest.mark.parametrize("failure", ["check", "tool", "configuration"])
def test_native_cli_observes_real_failure_without_granting_readiness(
    diagnostic, failure, monkeypatch, capsys
):
    runtime, open_member, _ = diagnostic
    member = open_member(code="print('native check diagnostic'); raise SystemExit(9)")
    manifest = member / "signetum.toml"
    if failure == "tool":
        manifest.write_text(
            manifest.read_text() + '\n[[validation.tools]]\nname = "absent"\n'
            'identity_command = ["signetum-intentionally-absent-tool"]\n'
        )
    elif failure == "configuration":
        manifest.write_text(manifest.read_text().replace("protocol = 2", 'protocol = "two"'))
    commit_contribution(member)
    monkeypatch.chdir(member)
    code = {"check": 3, "tool": 4, "configuration": 2}[failure]
    assert runtime.main(["changed"]) == code
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    result = json.loads(captured.out)
    assert (
        result["status"]
        == {"check": "failed", "tool": "infrastructure_error", "configuration": "invalid"}[failure]
    )
    assert result["exit_code"] == code
    assert result["operation"] == "changed"
    assert result["expected"]
    assert Path(result["log"]).is_file()
    if failure == "check":
        assert "native check diagnostic" in captured.err
        assert "exited 9" in result["cause"]
    assert not (state_root(member) / "validation").exists()
