"""Shared disposable Git and Worktrunk effects for lifecycle contracts."""

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum import worktrunk as wt
from signetum.git import git_output
from signetum.operations import InfrastructureError
from signetum.runtime_generation import generate_runtime, runtime_problems
from signetum.workspaces import branch_name


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    """Prepare one immutable portable fixture before xdist starts its workers."""
    if hasattr(session.config, "workerinput"):
        return
    scaffold = Path(__file__).parents[1] / "tests/fixtures/portable-python"
    if runtime_problems(scaffold):
        generate_runtime(scaffold)


@pytest.fixture
def local_repository(tmp_path, monkeypatch):
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
        "schema_version = 3\n[signetum]\nprotocol = 2\n"
        '[repository]\narchitecture = "docs/ARCHITECTURE.md"\n'
        'changes = "changes"\n'
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
    policy = root / ".agents/signetum/repo.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("delivery:\n  branch: main\n")
    (root / "seed.txt").write_text("base\n")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "base")

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
        destination = None
        if arguments[0] == "--config-set":
            destination = Path(json.loads(arguments[1].split("=", 1)[1]))
            arguments = arguments[2:]
        if arguments[0] == "switch":
            branch = arguments[arguments.index("--create") + 1]
            base = arguments[arguments.index("--base") + 1]
            assert destination is not None
            path = destination
            path.parent.mkdir(parents=True, exist_ok=True)
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
        return [
            {
                "kind": "worktree",
                "branch": branch,
                "path": str(path),
                "branch_outcome": "deleted",
                "branch_checked_out_at": None,
            }
        ]

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
        str(Path(__file__).parents[1] / "tests/fixtures/portable-python/.agents/signetum/runtime")
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


@pytest.fixture
def record_source():
    kind = "example"
    return f'''[change]
schema_version = 1
id = "{kind}"
[change.source]
kind = "human_direction"
summary = "Preserve the original {kind} intent and rationale."
[change.contract]
version = 1
approved_base = "approved-base"
[[change.contract.requirements]]
id = "REQ-1"
outcome = "Expose the {kind} result."
acceptance = ["The existing entrypoint returns that result."]
[[change.contract.excluded]]
statement = "Publish a release."
reason = "Delivery authorization is separate."
[change.execution]
[[change.execution.steps]]
id = "STEP-1"
requirements = ["REQ-1"]
action = "Extend the current owner and verify its public entrypoint."
'''


@pytest.fixture
def repository(local_repository, tmp_path):
    root, state = local_repository
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git_output(remote, "init", "--bare")
    git_output(root, "remote", "add", "origin", str(remote))
    git_output(root, "push", "origin", "main")

    return root, state


@pytest.fixture(scope="session")
def _installed_payloads():
    return {}


@pytest.fixture
def installed_python(_installed_payloads, tmp_path_factory):
    wheels = tuple((Path(__file__).parents[1] / "dist").glob("signetum-*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]
    identity = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if identity not in _installed_payloads:
        root = tmp_path_factory.mktemp("installed payload with spaces")
        environment = root / "environment"
        python = environment / "bin/python"
        for command in (
            ["uv", "venv", "--python", sys.executable, str(environment)],
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
            [
                str(python),
                "-B",
                "-I",
                "-c",
                "from pathlib import Path; import sys,signetum; "
                "from importlib.util import find_spec; "
                "assert Path(signetum.__file__).is_relative_to(Path(sys.prefix)); "
                "assert find_spec('pydantic') is None",
            ],
        ):
            subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
        _installed_payloads[identity] = python
    return _installed_payloads[identity]
