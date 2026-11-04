"""The plugin guard refuses work-losing and protocol-bypassing commands from real payloads."""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from signetum.git import git_output

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/signetum/skills/signetum/scripts"
ENTRY = SCRIPTS / "command-guard"


def claude_payload(command: str, cwd: Path) -> dict[str, object]:
    """The shape Claude Code 2.1 sends to a plugin PreToolUse hook for Bash."""

    return {
        "session_id": "bd885105-ec2b-4b2e-8c22-27ad698217b9",
        "transcript_path": str(cwd / "transcript.jsonl"),
        "cwd": str(cwd),
        "prompt_id": "3e0e0b1d-3699-4457-90cb-52322cb7f2a7",
        "permission_mode": "default",
        "effort": {"level": "medium"},
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "Run a command"},
        "tool_use_id": "toolu_01X2Jrrv4oX9VpWB3jzJs9Dn",
    }


def codex_payload(command: str, cwd: Path) -> dict[str, object]:
    """The PreToolUseCommandInput codex-cli 0.166 serializes for exec_command."""

    return {
        "session_id": "019a4c1e-7d1b-7c30-9d2e-1b6f2f0c9a11",
        "turn_id": "turn-1",
        "transcript_path": None,
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "model": "gpt-5",
        "permission_mode": "default",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "call_1",
    }


@pytest.fixture
def guard(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("command_guard", SCRIPTS / "command_guard.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def run_guard(guard, monkeypatch, capsys, payload) -> tuple[int, dict[str, object] | None]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    code = guard.main()
    error = capsys.readouterr().err.strip()
    return code, json.loads(error) if error else None


BLOCKED = [
    ("git stash", "stash"),
    ("git stash push -m wip", "stash"),
    ("git stash pop", "stash"),
    ("git -C ../other stash", "stash"),
    ("git reset --hard origin/main", "destructive-reset"),
    ("git restore src/app.py", "destructive-restore"),
    ("git restore --staged --worktree src/app.py", "destructive-restore"),
    ("git clean -fdx", "destructive-restore"),
    ("git checkout -- src/app.py", "destructive-restore"),
    ("git checkout HEAD~1 -- src/app.py", "destructive-restore"),
    ("git checkout .", "destructive-restore"),
    ("git checkout -f main", "destructive-restore"),
    ("git switch --discard-changes main", "destructive-restore"),
    ("git switch -C topic", "destructive-restore"),
    ("git push --force origin topic", "force-push"),
    ("git push --force-with-lease origin topic", "force-push"),
    ("git push --force-with-lease=topic:abc origin topic", "force-push"),
    ("git -C /work/repo push -f origin topic", "force-push"),
    ("git push origin +topic", "force-push"),
    ("rm -rf .", "unbounded-delete"),
    ("rm -fr *", "unbounded-delete"),
    ("rm -r -f ~", "unbounded-delete"),
    ('rm -rf "$HOME"', "unbounded-delete"),
    ("rm -rf /", "unbounded-delete"),
    ("git merge main", "direct-merge"),
    ("git merge --abort", "direct-merge"),
    ("git rebase origin/main", "direct-rebase"),
    ("git -c core.editor=true rebase --continue", "direct-rebase"),
    ("wt step rebase", "direct-rebase"),
    ("wt step push", "direct-rebase"),
    ("wt merge main", "direct-merge"),
    ("git worktree remove ../topic", "direct-workspace-removal"),
    ("wt remove topic", "direct-workspace-removal"),
    ("git branch -D topic", "direct-workspace-removal"),
    ("git branch --delete --force topic", "direct-workspace-removal"),
    ("git worktree add ../topic", "direct-workspace-creation"),
    ("git worktree move ../topic ../elsewhere", "direct-workspace-creation"),
    ("wt switch -c topic", "direct-workspace-creation"),
    ("wt switch --create topic", "direct-workspace-creation"),
    # Reached through wrappers, chains, nested shells and substitutions.
    ("cd repo && git stash", "stash"),
    ("git status; git merge topic", "direct-merge"),
    ("git fetch || git rebase origin/main", "direct-rebase"),
    ("bash -lc 'git reset --hard'", "destructive-reset"),
    ('sh -c "cd x && git push --force"', "force-push"),
    ("eval git stash", "stash"),
    ("env GIT_TRACE=1 git stash", "stash"),
    ("FOO=1 command git merge topic", "direct-merge"),
    ("sudo -u build git clean -fd", "destructive-restore"),
    ("mise exec -- git rebase main", "direct-rebase"),
    ("timeout 30 git merge topic", "direct-merge"),
    ("echo $(git stash)", "stash"),
    ("echo `git stash`", "stash"),
    ('echo "$(git merge topic)"', "direct-merge"),
    ("( cd repo && git stash )", "stash"),
    ("for f in a; do git rebase main; done", "direct-rebase"),
    ("git status\ngit stash", "stash"),
    ("cat <<'EOF' | bash\ngit merge topic\nEOF", "direct-merge"),
    ("bash <<EOF\ngit stash\nEOF", "stash"),
]

ALLOWED = [
    "git status",
    "git log --oneline -5",
    "git diff HEAD~1",
    "git show HEAD",
    "git rev-parse HEAD",
    "git branch --list",
    "git stash list",
    "git stash show -p",
    "git branch -d topic",
    "git branch -f topic main",
    "git commit -m 'fix: keep work'",
    'git commit -m "do not git reset --hard"',
    "git reset HEAD src/app.py",
    "git reset --soft HEAD~1",
    "git restore --staged src/app.py",
    "git clean -n",
    "git clean -fdn",
    "git checkout -b topic",
    "git checkout main",
    "git switch -c topic",
    "git switch main",
    "git push origin topic",
    "git push -u origin topic",
    "git merge-base HEAD main",
    "git merge-tree main topic",
    "git worktree list",
    "git worktree prune",
    "wt switch topic",
    "wt list",
    "rm -rf build",
    "rm -rf ./dist",
    "rm -f *.log",
    "rm -r .",
    'echo "git merge main"',
    "echo 'git stash; git reset --hard'",
    "printf '%s\\n' 'git push --force'",
    "grep -n 'git rebase' notes.md",
    "git log --grep merge",
    "cat <<'EOF' > notes.md\ngit merge topic\ngit stash\nEOF",
    "cat <<EOF\nrm -rf /\nEOF",
    "# git stash\ngit status",
    "git status 2>&1 | head -5",
    "python -c 'print(\"git merge\")'",
]


@pytest.mark.parametrize("shape", [claude_payload, codex_payload])
@pytest.mark.parametrize(("command", "category"), BLOCKED)
def test_refused_commands_name_their_category_and_operation(
    guard, monkeypatch, capsys, tmp_path, shape, command, category
):
    code, refusal = run_guard(guard, monkeypatch, capsys, shape(command, tmp_path))
    assert code == 2
    assert refusal is not None
    assert refusal["guard"] == "signetum"
    assert refusal["category"] == category
    assert refusal["use"] == guard.USE[category]


@pytest.mark.parametrize("shape", [claude_payload, codex_payload])
@pytest.mark.parametrize("command", ALLOWED)
def test_read_only_and_mentioning_commands_run(
    guard, monkeypatch, capsys, tmp_path, shape, command
):
    assert run_guard(guard, monkeypatch, capsys, shape(command, tmp_path)) == (0, None)


def test_rm_of_the_real_home_is_refused_by_path(guard, monkeypatch, capsys, tmp_path):
    payload = claude_payload("rm -rf " + str(Path.home()), tmp_path)
    assert run_guard(guard, monkeypatch, capsys, payload)[0] == 2


def test_pre_commit_runs_only_when_the_payload_tree_has_no_unstaged_change(
    guard, monkeypatch, capsys, tmp_path
):
    repository = tmp_path / "repository"
    repository.mkdir()
    git_output(repository, "init", "-b", "main")
    git_output(repository, "config", "user.name", "Guard test")
    git_output(repository, "config", "user.email", "guard@example.invalid")
    (repository / "app.py").write_text("value = 1\n")
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "base")
    for command in ("pre-commit run --all-files", "uv run pre-commit run", "pre-commit"):
        assert run_guard(guard, monkeypatch, capsys, codex_payload(command, repository)) == (
            0,
            None,
        )
    (repository / "app.py").write_text("value = 2\n")
    for command in (
        "pre-commit run --all-files",
        "uv run --no-sync pre-commit run --files app.py",
        "env SKIP=ruff uv run pre-commit run",
        "python -m pre_commit run",
    ):
        code, refusal = run_guard(guard, monkeypatch, capsys, claude_payload(command, repository))
        assert code == 2
        assert refusal is not None and refusal["category"] == "pre-commit-dirty-tree"
    outside = codex_payload(f"cd {repository} && pre-commit run", tmp_path)
    assert run_guard(guard, monkeypatch, capsys, outside)[0] == 2
    allowed = ("pre-commit install", "git commit -m change", "echo pre-commit run")
    for command in allowed:
        assert run_guard(guard, monkeypatch, capsys, claude_payload(command, repository)) == (
            0,
            None,
        )


def _entry(payload: str, path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- shipped guard entry through a fixed shell
        ["/bin/sh", str(ENTRY)],
        input=payload,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": path},
        timeout=30,
        check=False,
    )


def _interpreter_path(tmp_path: Path, python: str) -> str:
    directory = tmp_path / ("bin-" + Path(python).name)
    directory.mkdir()
    (directory / "python3").symlink_to(python)
    return os.pathsep.join((str(directory), "/usr/bin", "/bin"))


def test_the_sh_entry_blocks_with_exit_two_and_otherwise_allows(tmp_path):
    path = _interpreter_path(tmp_path, sys.executable)
    blocked = _entry(json.dumps(claude_payload("git -C x stash", tmp_path)), path)
    assert blocked.returncode == 2
    assert json.loads(blocked.stderr)["category"] == "stash"
    assert _entry(json.dumps(codex_payload("git status", tmp_path)), path).returncode == 0
    assert _entry("not json", path).returncode == 0
    assert _entry(json.dumps({"tool_input": "unexpected"}), path).returncode == 0
    empty = tmp_path / "empty"
    empty.mkdir()
    missing = _entry(json.dumps(claude_payload("git stash", tmp_path)), str(empty))
    assert missing.returncode == 0


def test_a_crashing_guard_allows_the_command(tmp_path):
    crashing = tmp_path / "crashing"
    crashing.mkdir()
    (crashing / "python3").write_text("#!/bin/sh\nexit 1\n")
    (crashing / "python3").chmod(0o755)
    path = os.pathsep.join((str(crashing), "/usr/bin", "/bin"))
    assert _entry(json.dumps(claude_payload("git stash", tmp_path)), path).returncode == 0


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system Python 3")
def test_the_guard_runs_under_the_system_python(tmp_path):
    system = shutil.which("python3", path="/usr/bin")
    assert system is not None
    path = _interpreter_path(tmp_path, system)
    for shape in (claude_payload, codex_payload):
        blocked = _entry(json.dumps(shape("git push --force-with-lease", tmp_path)), path)
        assert blocked.returncode == 2, blocked.stderr
        assert json.loads(blocked.stderr)["category"] == "force-push"
        quoted = _entry(json.dumps(shape('echo "git merge main"', tmp_path)), path)
        assert quoted.returncode == 0, quoted.stderr
