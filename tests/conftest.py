"""Shared disposable Git and Worktrunk effects for lifecycle contracts."""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum import worktrunk as wt
from signetum.git import git_output
from signetum.operations import InfrastructureError
from signetum.workspaces import branch_name


@pytest.fixture
def repository(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    root.mkdir()
    git_output(root, "init", "-b", "main")
    git_output(root, "config", "user.name", "Workspace Test")
    git_output(root, "config", "user.email", "workspace@example.invalid")
    state = tmp_path / "preparation"
    state.mkdir()
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; p=Path(sys.argv[1]); "
        "n=p/'attempts'; n.write_text(str(int(n.read_text())+1) if n.exists() else '1'); "
        "sys.exit(13 if (p/'fail').exists() else 0)",
        str(state),
    ]
    (root / "signetum.toml").write_text(
        'schema_version = 2\n[signetum]\nprotocol = 2\ntemplate_version = "0.2.0"\n'
        '[repository]\narchitecture = "docs/ARCHITECTURE.md"\n'
        'specifications = "changes/*/specs/*.toml"\nplans = "changes/*/plans/*.md"\n'
        'decisions = "docs/decisions"\n'
        '[[impact.rules]]\nname = "all"\npaths = ["**"]\nshards = ["test:check"]\n'
        '[validation]\nmember_required = ["test:check"]\n'
        '[[validation.shards]]\nname = "test:check"\ncommand = ["true"]\n'
        '[[validation.shards]]\nname = "test:prepare"\ncommand = ' + json.dumps(command) + "\n"
        '[[validation.gates]]\nname = "prepare"\nshards = ["test:prepare"]\n'
        '[[validation.gates]]\nname = "member"\nshards = ["test:check"]\n'
        '[[validation.gates]]\nname = "final"\nshards = ["test:check"]\n'
        '[[validation.gates]]\nname = "batch"\nshards = ["test:check"]\n'
    )
    policy = root / ".agents/repo-dev/repo.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("delivery:\n  branch: main\n")
    (root / "seed.txt").write_text("base\n")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "base")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git_output(remote, "init", "--bare")
    git_output(root, "remote", "add", "origin", str(remote))
    git_output(root, "push", "origin", "main")

    def native_worktrunk(repository, arguments, *, json_output=False):
        del json_output
        if arguments[0] == "list":
            items = []
            for block in git_output(root, "worktree", "list", "--porcelain").split("\n\n"):
                fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
                branch = fields.get("branch", "").removeprefix("refs/heads/")
                if not branch:
                    continue
                path = Path(fields["worktree"])
                items.append(
                    {
                        "branch": branch,
                        "head": {"sha": fields["HEAD"]},
                        "worktree": {
                            "path": str(path),
                            "changes": {
                                "modified": bool(git_output(path, "status", "--porcelain")),
                            },
                        },
                    }
                )
            return {"schema": 2, "items": items}
        if arguments[0] == "switch":
            branch = arguments[arguments.index("--create") + 1]
            base = arguments[arguments.index("--base") + 1]
            path = tmp_path / ("wt-" + branch.replace("/", "-"))
            assert "--no-hooks" in arguments and "--no-cd" in arguments
            git_output(root, "worktree", "add", "-b", branch, str(path), base)
            return {}
        assert arguments[0] == "remove"
        assert {"--foreground", "--no-hooks", "--force-delete"} <= set(arguments)
        path = Path(arguments[-2])
        branch = branch_name(path)
        git_output(
            root, "worktree", "remove", *(("--force",) if "--force" in arguments else ()), str(path)
        )
        git_output(root, "branch", "-D", branch)
        return {"kind": "worktree", "branch_outcome": "deleted"}

    def native_preparation(repository, command, **kwargs):
        result = subprocess.run(
            command,
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=kwargs["timeout_seconds"],
        )
        if result.returncode:
            raise InfrastructureError(f"fixture preparation exited {result.returncode}")
        return result

    monkeypatch.setattr(wt, "worktrunk", native_worktrunk)
    monkeypatch.setattr(wt, "run_tool", native_preparation)
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[1] / "template/.agents/repo-dev/runtime")
    )
    copied = importlib.import_module("_signetum_runtime.worktrunk")
    copied_errors = importlib.import_module("_signetum_runtime.operations")

    def copied_preparation(repository, command, **kwargs):
        try:
            return native_preparation(repository, command, **kwargs)
        except InfrastructureError as error:
            raise copied_errors.InfrastructureError(str(error)) from error

    monkeypatch.setattr(copied, "worktrunk", native_worktrunk)
    monkeypatch.setattr(copied, "run_tool", copied_preparation)

    return root, state
