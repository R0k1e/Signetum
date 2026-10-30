from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from change_fixtures import commit_approval

from signetum import lifecycle as engine_lifecycle
from signetum.git import git_output
from signetum.workspaces import WorkspaceRecord, branch_name, read_record, state_root, write_record

ROOT = Path(__file__).resolve().parents[2]


def _template_lifecycle() -> ModuleType:
    directory = ROOT / "template/.agents/repo-dev/runtime"
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    return importlib.import_module("_signetum_runtime.lifecycle")


@pytest.fixture
def template_admission_member(repository, tmp_path):
    root, state = repository
    runtime = _template_lifecycle()
    (state / "tool").write_text("v1")
    manifest = root / "signetum.toml"
    text = (
        manifest.read_text()
        .replace(
            "[repository]",
            'evidence_protocol = "reposeal.validation-evidence@3"\n'
            + 'evidence_schema_digest = "sha256:'
            + "0" * 64
            + '"\n[repository]',
        )
        .replace('name = "test:check"\n', 'name = "test:check"\nrequires = ["test:prepare"]\n')
    )
    text = text.replace(
        'decisions = "docs/decisions"',
        'decisions = "docs/decisions"\nlockfiles = ["fixture.lock"]',
    )
    (root / "fixture.lock").write_text("locked input\n")
    text += '\n[[impact.rules]]\nname = "docs"\npaths = ["docs/**"]\nrequires_final = true\n'
    tool = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())",
        str(state / "tool"),
    ]
    text += (
        '\n[[validation.tools]]\nname = "fixture"\nidentity_command = ' + json.dumps(tool) + "\n"
    )
    manifest.write_text(text)
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare admission boundary")
    base = git_output(root, "rev-parse", "HEAD")
    member = tmp_path / "member"
    git_output(root, "worktree", "add", "-b", "plan/template-admission", str(member), base)
    write_record(state_root(root), WorkspaceRecord(1, "plan/template-admission", base, "member"))
    commit_approval(member)
    (member / "docs").mkdir()
    (member / "docs/note.md").write_text("approved implementation\n")
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "implement approved change")
    return runtime, member, state, base


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "same-tree-tip",
        "dependency",
        "tool",
        "schema",
        "world",
        "gate",
        "base",
        "configuration",
        "profiles",
        "graph",
        "lockfiles",
        "duplicate-fields",
        "invalid-encoding",
        "extensions-type",
    ],
)
def test_native_template_admission_requires_exact_member_inputs(template_admission_member, damage):
    runtime, member, state, _ = template_admission_member
    if damage != "missing":
        ready = runtime.validate(member, "member")
        path = Path(ready["receipt"])
        assert (
            runtime._admission_evidence(
                member,
                git_output(member, "rev-parse", "HEAD"),
                runtime.load_manifest(member / "signetum.toml"),
            )
            == path.name
        )
        payload = json.loads(path.read_text())
        if damage == "duplicate-fields":
            source = json.dumps(payload)
            assert '"extensions": {' in source
            path.write_text(
                source.replace(
                    '"extensions": {', '"extensions": {"duplicate": false, "duplicate": true,', 1
                )
            )
        elif damage == "invalid-encoding":
            path.write_bytes(b"\xff")
        elif damage == "same-tree-tip":
            git_output(member, "commit", "--amend", "-m", "reworded implementation")
        elif damage == "tool":
            (state / "tool").write_text("v2")
        else:
            evidence = payload["evidence"]
            if damage == "extensions-type":
                evidence["extensions"] = "not-an-object"
            elif damage == "dependency":
                evidence["execution"]["shards"] = [
                    item
                    for item in evidence["execution"]["shards"]
                    if item["name"] != "test:prepare"
                ]
            elif damage == "schema":
                evidence["schema_digest"] = "sha256:" + "f" * 64
            elif damage in {"base", "configuration", "profiles", "graph", "lockfiles"}:
                values = {
                    "base": "f" * 40,
                    "configuration": {"path": "signetum.toml", "digest": "sha256:" + "f" * 64},
                    "profiles": ["different@1"],
                    "graph": "sha256:" + "f" * 64,
                    "lockfiles": [{"path": "fixture.lock", "digest": "sha256:" + "f" * 64}],
                }
                evidence["identity"][damage] = values[damage]
            elif damage == "world":
                for item in evidence["execution"]["shards"]:
                    item.update(evidence="world", observed_at="2026-10-29T00:00:00Z")
            else:
                evidence["execution"]["gates"] = ["unrelated"]
            path.write_text(json.dumps(payload))
    tip = git_output(member, "rev-parse", "HEAD")
    with pytest.raises(runtime.AdmissionError, match="no evidence proving its selected"):
        runtime._admission_evidence(member, tip, runtime.load_manifest(member / "signetum.toml"))


def test_native_template_accepts_complete_final_evidence(template_admission_member):
    runtime, member, _, base = template_admission_member
    tip = git_output(member, "rev-parse", "HEAD")
    repository_api = importlib.import_module("_signetum_runtime.repository")
    graph, inputs = runtime._runtime_validation(runtime.load_manifest(member / "signetum.toml"))

    evidence, raw_path = repository_api.run_repository_gate(
        member, graph, "final", replace(inputs, base=base), runtime._receipt_root(member)
    )
    path = raw_path.with_name(raw_path.name.replace("final-", "final-lifecycle-"))
    path.write_text(
        json.dumps({"kind": "final", "valid": True, "evidence": json.loads(evidence.to_json())})
    )
    assert (
        runtime._admission_evidence(member, tip, runtime.load_manifest(member / "signetum.toml"))
        == path.name
    )


def test_template_passes_actual_bounded_worker_count_to_its_command(tmp_path, monkeypatch):
    # This case supplies standalone host capacity; nested-lane behavior has its own public case.
    monkeypatch.delenv("SIGNETUM_VALIDATION_WORKERS", raising=False)
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    runtime = _template_lifecycle()
    resources = importlib.import_module("_signetum_runtime.resources")
    monkeypatch.setattr(
        resources, "observe_resources", lambda: resources.ResourceObservation(2, 3000)
    )
    script = (
        "import os; from pathlib import Path; "
        "Path('workers').write_text(os.environ['SIGNETUM_VALIDATION_WORKERS'])"
    )
    result = runtime.RepositoryValidationAdapter(tmp_path).run_shard(
        importlib.import_module("_signetum_runtime.validation").ValidationShard(
            "test:bounded", (sys.executable, "-c", script), workers=8, worker_memory_mb=1000
        )
    )
    assert result.succeeded, result.diagnostic
    assert (tmp_path / "workers").read_text() == "2"
    assert result.details["resource_allocation"]["workers"] == 2


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
        monkeypatch.setattr(runtime, "_require_clean", lambda repository: None)
        monkeypatch.setattr(
            runtime, "run_diagnostic_gate", lambda *args, **kwargs: {"executed": []}
        )
        monkeypatch.setattr(
            runtime,
            "member_contribution_paths",
            lambda *args, paths=tuple(vector["files"]): paths,
        )
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
    git_output(tmp_path, "init")
    common = Path(git_output(tmp_path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    assert runtime._receipt_root(tmp_path) == common / "signetum" / "validation"


def test_template_batch_is_created_with_its_final_role(repository, monkeypatch):
    root, _ = repository
    runtime = _template_lifecycle()
    monkeypatch.setattr(runtime, "admit", lambda batch, members: {})
    base = git_output(root, "rev-parse", "HEAD")
    declared = (root,)
    opened = runtime.batch_open(root, declared)
    batch = Path(opened["worktree"])
    branch = branch_name(batch)
    record = read_record(state_root(root), branch)
    assert record.kind == "batch"
    assert record.base == base
    assert record.members == ("main",)
    owner = importlib.import_module("_signetum_runtime.workspaces")
    path = owner.record_path(owner.state_root(root), branch)
    before = path.read_bytes()
    with pytest.raises(owner.WorkspaceError, match="different recorded identity"):
        owner.write_record(owner.state_root(root), owner.WorkspaceRecord(1, branch, base, "member"))
    assert path.read_bytes() == before
