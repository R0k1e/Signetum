"""Real local utilities exercise source-bound selection and partition execution."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from change_fixtures import consolidated_approval

from signetum import lifecycle
from signetum.adoption import AdoptionRequest, apply, plan_digest, preview
from signetum.ci_partitions import (
    PartitionPlan,
    PartitionResult,
    combine,
    create_plan,
    run_partition,
)
from signetum.evidence.receipts import ArtifactIdentity
from signetum.git import git_output
from signetum.manifest import load_manifest
from signetum.selection_request import SelectionInput, SelectionRequest
from signetum.serialization import contract_mapping, dataclass_from_mapping, load_json
from signetum.validation.repository import configured_validation
from signetum.workspaces import WorkspaceRecord, state_root, write_record

ROOT = Path(__file__).parents[2]


def _commit(root, message):
    git_output(root, "add", ".")
    git_output(root, "commit", "--allow-empty", "-m", message)
    return git_output(root, "rev-parse", "HEAD")


def _cli(root, *args, portable=False):
    prefix = (
        [sys.executable, "-I", "-S", str(root / ".agents/repo-dev/runtime/protocol.py")]
        if portable
        else [sys.executable, "-m", "signetum.cli", "protocol"]
    )
    return subprocess.run(  # noqa: S603 -- private consumer, actual engine or generated utility
        [*prefix, *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def consumer(local_repository):
    root, _ = local_repository
    architecture = root / "docs/ARCHITECTURE.md"
    architecture.parent.mkdir()
    architecture.write_text("# Existing architecture\n")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    request = AdoptionRequest(
        manifest=(root / "signetum.toml").read_text(),
        policy=(root / ".agents/repo-dev/repo.yaml").read_text(),
        interpreter=(sys.executable, "-I", "-S"),
    )
    proposal = preview(root, request)
    apply(root, proposal, plan_digest(proposal))
    _commit(root, "adopt local utilities")
    return root


def test_generated_python_provider_selects_real_import_dependents_and_ready_uses_it(consumer):
    root = consumer
    (root / "app").mkdir()
    (root / "tests/unit").mkdir(parents=True)
    (root / "app/feature.py").write_text("def twice(x): return x*2\n")
    (root / "tests/unit/test_feature.py").write_text(
        'import sys; sys.path.insert(0,"app")\n'
        "from feature import twice\ndef test_twice(): assert twice(2)==4\n"
    )
    (root / "tests/unit/test_other.py").write_text("def test_other(): assert False\n")
    config = root / "python-selection.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_roots": ["app"],
                "unit_roots": ["tests/unit"],
                "unit_shard": "test:check",
            }
        )
    )
    manifest = root / "signetum.toml"
    command = [sys.executable, "-m", "pytest", "--no-cov", "-q", "tests/unit"]
    text = manifest.read_text().replace(
        'name = "test:check"\ncommand = ["true"]',
        'name = "test:check"\ncommand = ' + json.dumps(command),
    )
    text = text.replace('paths = ["**"]', 'paths = ["app/**", "tests/unit/**"]')
    text += '\n[[impact.rules]]\nname="records"\npaths=["changes/**"]\nshards=[]\n'
    text += (
        """
[impact.provider]
protocol="signetum.selection@1"
entrypoint=".agents/repo-dev/runtime/protocol.py"
command=["""
        + json.dumps(sys.executable)
        + ""","-I","-S","{selector}","select-python","--config","python-selection.json"]
inputs=["python-selection.json", ".agents/repo-dev/runtime/_signetum_runtime/python_selection.py"]
tools=[{name="python-selector",identity_command=["""
        + json.dumps(sys.executable)
        + ""","--version"]}]
[[impact.provider.targets]]
shard="test:check"
roots=["tests/unit"]
argument_index=5
"""
    )
    manifest.write_text(text)
    base = _commit(root, "declare optional Python selection")
    git_output(root, "switch", "-c", "plan/fine-selection")
    write_record(state_root(root), WorkspaceRecord(1, "plan/fine-selection", base, "member"))
    consolidated_approval(root, base)
    _commit(root, "approve selected change")
    (root / "app/feature.py").write_text("def twice(x): return x+x\n")
    _commit(root, "implement behavior")
    changed = lifecycle.changed(root, True)
    assert changed["checks_started"] is False
    graph, inputs = configured_validation(load_manifest(manifest))
    source = git_output(root, "rev-parse", "HEAD")
    wire = SelectionRequest(
        protocol="signetum.selection@1",
        source=source,
        tree=git_output(root, "rev-parse", "HEAD^{tree}"),
        base=base,
        files=("app/feature.py", "changes/example/change.toml"),
        graph=graph,
        profiles=inputs.profiles,
        tools=(),
        inputs=(
            SelectionInput(
                artifact=ArtifactIdentity.from_bytes("python-selection.json", config.read_bytes()),
                blob=git_output(root, "rev-parse", "HEAD:python-selection.json"),
            ),
        ),
    )
    produced = subprocess.run(  # noqa: S603 -- same wire contract through the engine, no judged-tree imports
        [
            sys.executable,
            "-m",
            "signetum.cli",
            "protocol",
            "select-python",
            "--config",
            str(config),
        ],
        input=json.dumps(contract_mapping(wire)),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert produced.returncode == 0, produced.stdout + produced.stderr
    assert json.loads(produced.stdout)["targets"][0]["tests"] == [
        {"path": "tests/unit/test_feature.py", "argument": "tests/unit/test_feature.py"}
    ]
    ready = lifecycle.validate(root, "member")
    assert ready["status"] == "ready"
    outcome = _cli(root, "status", portable=True)
    assert outcome.returncode == 0, outcome.stdout + outcome.stderr
    status = json.loads(outcome.stdout)
    assert status["receipts"][0]["source_current"] is True
    assert status["workspace"]["kind"] == "member"
    # Unknown input must remove narrowing; the existing unselected failure is then observed.
    (root / "unknown.dat").write_text("unowned input")
    _commit(root, "expose unknown coverage")
    with pytest.raises(lifecycle.ValidationExecutionError, match="test:check"):
        lifecycle.validate(root, "member")


def test_ci_plan_runs_exact_files_and_refuses_failed_stale_or_incomplete_results(
    consumer, tmp_path
):
    root = consumer
    (root / "checks").mkdir()
    (root / "checks/test_a.py").write_text("assert 1+1==2\n")
    (root / "checks/test_b.py").write_text("assert 2+2==4\n")
    config = root / "partitions.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "shard": "test:check",
                "roots": ["checks"],
                "patterns": ["checks/test_*.py"],
                "argument_index": 3,
                "slices": 2,
            }
        )
    )
    manifest = root / "signetum.toml"
    command = [
        sys.executable,
        "-c",
        "import runpy,sys; [runpy.run_path(p) for p in sys.argv[1:]]",
        "checks",
    ]
    manifest.write_text(
        manifest.read_text()
        .replace(
            'decisions = "docs/decisions"',
            'decisions = "docs/decisions"\nlockfiles=["partitions.json"]',
        )
        .replace(
            'name = "test:check"\ncommand = ["true"]',
            'name = "test:check"\ncommand = ' + json.dumps(command),
        )
    )
    _commit(root, "declare source-bound partitions")
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "lane.json"
    planned = _cli(root, "partition", "plan", "--config", str(config), "--output", str(plan_path))
    assert planned.returncode == 0, planned.stdout + planned.stderr
    assert json.loads(planned.stdout)["partitions"] == 2
    result = _cli(
        root, "partition", "run", "--plan", str(plan_path), "--index", "0", "--output", str(output)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    plan = dataclass_from_mapping(PartitionPlan, load_json(plan_path.read_text()))
    second = run_partition(root, plan, 1)
    first = dataclass_from_mapping(PartitionResult, load_json(output.read_text()))
    assert combine(plan, (first, second), job_statuses=("success", "success"))["files"] == 2
    second_path = tmp_path / "other.json"
    second_path.write_text(json.dumps(contract_mapping(second)))
    combined = _cli(
        root,
        "partition",
        "combine",
        "--plan",
        str(plan_path),
        "--result",
        str(output),
        "--result",
        str(second_path),
        "--job-status",
        "success",
        "--job-status",
        "success",
    )
    assert combined.returncode == 0, combined.stdout + combined.stderr
    assert json.loads(combined.stdout)["authority"] == "ci_diagnostic_only"
    incomplete = _cli(
        root, "partition", "combine", "--plan", str(plan_path), "--result", str(output)
    )
    assert incomplete.returncode == 2
    assert "expected" in json.loads(incomplete.stdout)
    _commit(root, "advance unrelated source")
    stale = _cli(root, "partition", "run", "--plan", str(plan_path), "--index", "0")
    assert stale.returncode == 2 and "current source" in json.loads(stale.stdout)["cause"]
    (root / "checks/test_b.py").write_text("assert False\n")
    _commit(root, "introduce real failed check")
    fresh = create_plan(root, config)
    fresh_path = tmp_path / "fresh.json"
    fresh_path.write_text(json.dumps(contract_mapping(fresh)))
    failed_path = tmp_path / "failed.json"
    failed_cli = _cli(
        root,
        "partition",
        "run",
        "--plan",
        str(fresh_path),
        "--index",
        "1",
        "--output",
        str(failed_path),
    )
    assert failed_cli.returncode == 3 and "expected" in json.loads(failed_cli.stdout)
    failed = dataclass_from_mapping(PartitionResult, load_json(failed_path.read_text()))
    assert not failed.passed
    with pytest.raises(ValueError):
        combine(fresh, (run_partition(root, fresh, 0), failed), job_statuses=("success", "success"))
    with pytest.raises(ValueError, match="index"):
        run_partition(root, fresh, 2)
