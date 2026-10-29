"""Subprocess evidence for failed-node-only serial recovery."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from signetum.git import git_output
from signetum.validation import (
    GateDeclaration,
    GraphContribution,
    ValidationShard,
    resolve_validation_graph,
)
from signetum.validation.execution import ValidationExecutionError, ValidationInputs
from signetum.validation.repository import run_repository_gate


@pytest.fixture(params=["engine", "template"])
def runner_command(request):
    if request.param == "engine":
        return ["-m", "signetum.validation.pytest_runner"]
    runner = Path(__file__).parents[2] / (
        "template/.agents/repo-dev/runtime/_signetum_runtime/pytest_runner.py"
    )
    return [str(runner)]


@pytest.mark.parametrize("retry", ["pass", "fail", "skip"])
def test_retry_requires_passed_call_and_retains_first_failure(tmp_path, retry, runner_command):
    test = tmp_path / "test_example.py"
    test.write_text(
        "from pathlib import Path\nimport pytest,sys\n"
        "@pytest.mark.parametrize('identity', ['user@example'])\n"
        "def test_flaky(identity):\n"
        "    assert 'signetum' not in sys.modules, 'pytest depends on engine installation'\n"
        "    marker = Path(__file__).with_suffix('.attempt')\n"
        "    first = not marker.exists()\n"
        "    marker.touch()\n"
        "    if first: assert False, 'first failure retained'\n"
        + ("    pytest.skip('cannot prove recovery')\n" if retry == "skip" else "")
        + ("    assert False, 'persistent failure'\n" if retry == "fail" else "")
        + "def test_unrelated():\n"
        "    marker = Path(__file__).with_suffix('.unrelated')\n"
        "    assert not marker.exists(), 'unrelated test ran twice'\n"
        "    marker.touch()\n"
    )
    report = tmp_path / "recovery.json"
    result = subprocess.run(  # noqa: S603 -- isolated Python fixture, no shell
        [
            sys.executable,
            *runner_command,
            "--",
            "-q",
            "-o",
            "addopts=",
            str(test),
        ],
        env=dict(os.environ, SIGNETUM_RECOVERY_REPORT=str(report)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    defects = json.loads(report.read_text())
    if retry == "pass":
        assert len(defects) == 1
        assert "first failure retained" in str(defects[0]["first_failure"])
    else:
        assert defects == []


@pytest.mark.parametrize("workers", [0, 2])
def test_collection_failure_is_not_retried(tmp_path, workers, runner_command):
    test = tmp_path / "test_broken.py"
    test.write_text("raise RuntimeError('collection failed')\n")
    report = tmp_path / "recovery.json"
    result = subprocess.run(  # noqa: S603 -- isolated Python fixture, no shell
        [
            sys.executable,
            *runner_command,
            "--",
            "-q",
            "-o",
            "addopts=",
            str(test),
        ],
        env=dict(
            os.environ,
            SIGNETUM_RECOVERY_REPORT=str(report),
            SIGNETUM_VALIDATION_WORKERS=str(workers),
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (1 if workers else 2)
    assert "collection failed" in result.stdout
    assert not report.exists()


def test_parallel_failure_retries_without_a_worker(tmp_path, runner_command):
    pytest.importorskip("xdist", reason="parallel adapter scenario requires optional pytest-xdist")
    test = tmp_path / "test_parallel.py"
    test.write_text(
        "import os\n"
        "def test_parallel():\n"
        "    assert 'PYTEST_XDIST_WORKER' not in os.environ, 'first parallel failure'\n"
    )
    report = tmp_path / "recovery.json"
    result = subprocess.run(  # noqa: S603 -- isolated Python fixture, no shell
        [
            sys.executable,
            *runner_command,
            "--",
            "-q",
            "-o",
            "addopts=",
            "-n2",
            str(test),
        ],
        env=dict(os.environ, SIGNETUM_RECOVERY_REPORT=str(report)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "first parallel failure" in str(json.loads(report.read_text()))


def test_failed_original_never_writes_success_even_with_a_one_run_window(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitignore").write_text("__pycache__/\n")
    state = tmp_path / "attempts"
    (repository / "signetum.toml").write_text("schema_version = 2\n")
    (repository / "test_retry.py").write_text(
        "from pathlib import Path\n"
        "def test_retry():\n"
        f"    state = Path({str(state)!r})\n"
        "    n = int(state.read_text()) if state.exists() else 0\n"
        "    state.write_text(str(n + 1))\n"
        "    assert n % 2, 'recurring contention failure'\n"
    )
    git_output(repository, "init")
    git_output(repository, "add", ".")
    git_output(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    graph = resolve_validation_graph(
        (
            GraphContribution(
                "test",
                (
                    ValidationShard(
                        "test:pytest",
                        (
                            sys.executable,
                            "-m",
                            "signetum.validation.pytest_runner",
                            "--",
                            "-q",
                            "-o",
                            "addopts=",
                            "test_retry.py",
                        ),
                    ),
                ),
                (GateDeclaration("member", ("test:pytest",)),),
            ),
        )
    )
    inputs = ValidationInputs("signetum.toml", (), (), (), recovery_threshold=2)
    receipts = tmp_path / "receipts"
    for policy in (inputs, replace(inputs, recovery_window=1)):
        with pytest.raises(ValidationExecutionError, match="recurring contention failure"):
            run_repository_gate(repository, graph, "member", policy, receipts)
        assert not tuple(receipts.glob("member-*.json"))


def test_independent_template_retains_recovery_and_refuses_a_repeated_node(repository, tmp_path):
    root, _ = repository
    runtime = Path(__file__).parents[2] / "template/.agents/repo-dev/runtime"
    state = tmp_path / "template-attempts"
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (root / "test_retry.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "def test_retry():\n"
        "    assert 'signetum' not in sys.modules\n"
        f"    state = Path({str(state)!r})\n"
        "    n = int(state.read_text()) if state.exists() else 0\n"
        "    state.write_text(str(n + 1))\n"
        "    assert n % 2, 'recurring template failure'\n"
    )
    command = [
        sys.executable,
        str(runtime / "_signetum_runtime/pytest_runner.py"),
        "--",
        "-q",
        "-o",
        "addopts=",
        "test_retry.py",
    ]
    manifest = root / "signetum.toml"
    manifest.write_text(
        'schema_version = 2\n[signetum]\nprotocol = 2\ntemplate_version = "0.2.0"\n'
        'evidence_protocol = "reposeal.validation-evidence@3"\n'
        'evidence_schema_digest = "sha256:' + "0" * 64 + '"\n'
        '[repository]\narchitecture = "docs/ARCHITECTURE.md"\n'
        'specifications = "changes/*/specs/*.toml"\nplans = "changes/*/plans/*.md"\n'
        'decisions = "docs/decisions"\n'
        "[validation]\nrecovery_threshold = 2\nrecovery_window = 20\n"
        '[[validation.shards]]\nname = "test:pytest"\ncommand = ' + json.dumps(command) + "\n"
        '[[validation.gates]]\nname = "member"\nshards = ["test:pytest"]\n'
        '[[validation.gates]]\nname = "final"\nshards = ["test:pytest"]\n'
    )
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare template recovery fixture")
    script = """
import json,sys
from datetime import UTC,datetime
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from _signetum_runtime import lifecycle
repository=Path(sys.argv[2])
try:
    from _signetum_runtime.repository import run_repository_gate
    graph,inputs=lifecycle._runtime_validation(lifecycle.load_manifest(repository/'signetum.toml'))
    receipt,_=run_repository_gate(repository,graph,'member',inputs,lifecycle._receipt_root(repository))
except lifecycle.ValidationExecutionError as error:
    print(json.dumps({'reason':str(error)}))
    raise SystemExit(3)
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules
print(receipt.to_json(),end='')
"""

    def run():
        return subprocess.run(  # noqa: S603 -- isolated consumer and native fixture pytest
            [sys.executable, "-I", "-S", "-c", script, str(runtime), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )

    first = run()
    assert first.returncode == 3, first.stdout + first.stderr
    assert "recurring template failure" in first.stdout
    assert "diagnostic retry passed" in first.stdout
    manifest.write_text(manifest.read_text().replace("recovery_window = 20", "recovery_window = 1"))
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "bound recovery history to the current observation")
    bounded = run()
    assert bounded.returncode == 3, bounded.stdout + bounded.stderr
