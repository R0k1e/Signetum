"""Structured whole-corpus checks compare against verified member baselines."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from change_fixtures import commit_approval
from test_workspace_operations import commit_file, opened

from signetum import lifecycle
from signetum import workspace_operations as ops
from signetum.git import git_output
from signetum.operations import MergeConflict
from signetum.profiles.ty import ty_document
from signetum.resources.schemas import evidence_schema_digest
from signetum.synchronization import member_contribution_paths
from signetum.validation.diagnostic_protocol import diagnostic_multiset
from signetum.validation.diagnostics import traceability_document
from signetum.validation.execution import ValidationExecutionError, ValidationInfrastructureError
from signetum.validation.repository import run_repository_gate

OLD = {"file": "module.py", "rule": "old-rule", "message": "inherited problem", "line": 2}


def document(*diagnostics):
    return json.dumps({"schema_version": 1, "diagnostics": list(diagnostics)})


@pytest.fixture(params=["engine", "template"])
def runtime(request, monkeypatch):
    if request.param == "engine":
        return lifecycle
    directory = Path(__file__).parents[1] / "template/.agents/repo-dev/runtime"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "ratchet_template_lifecycle", directory / "lifecycle.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def execution_failure(runtime):
    return runtime.ValidationExecutionError


def admission(runtime, member, tip):
    if runtime is lifecycle:
        return runtime._admission_evidence(
            member, tip, lifecycle.load_manifest(member / "signetum.toml")
        )
    return runtime._admission_evidence(member, tip)


def configured(repository, *, baseline_report=None):
    root, state = repository
    script = (
        "import json, sys\nfrom pathlib import Path\n"
        f"log=Path({str(state / 'runs')!r})\n"
        "with log.open('a') as stream: stream.write(str(Path.cwd())+'\\n')\n"
        "raw=Path('diagnostics.json').read_text() if Path('diagnostics.json').exists() "
        "else json.dumps({'schema_version':1,'diagnostics':[]})\n"
        "if sys.argv[1]=='report': print(raw)\n"
        "else: sys.exit(1 if json.loads(raw)['diagnostics'] else 0)\n"
    )
    (root / "checker.py").write_text(script)
    (root / "diagnostics.json").write_text(
        document(OLD) if baseline_report is None else baseline_report
    )
    manifest = root / "signetum.toml"
    strict = json.dumps([sys.executable, "checker.py", "strict"])
    report = json.dumps([sys.executable, "checker.py", "report"])
    manifest.write_text(
        manifest.read_text()
        .replace(
            "[repository]",
            'evidence_protocol = "reposeal.validation-evidence@3"\n'
            + f'evidence_schema_digest = "{evidence_schema_digest()}"\n[repository]',
        )
        .replace(
            'name = "test:check"\ncommand = ["true"]',
            f'name = "test:check"\ncommand = {strict}\nratchet_command = {report}',
        )
    )
    (state / "tool").write_text("v1")
    identity = json.dumps(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())",
            str(state / "tool"),
        ]
    )
    manifest.write_text(
        manifest.read_text()
        + '\n[[validation.tools]]\nname = "fixture"\nidentity_command = '
        + identity
        + "\n"
    )
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare structured corpus check")
    member = opened(root, "plan/ratchet")
    commit_approval(member, "example")
    commit_file(member, "diagnostics.json", document({**OLD, "line": 42, "column": 8}))
    return root, member, state


def test_member_accepts_only_inherited_findings_and_final_remains_strict(repository, runtime):
    root, member, _ = configured(repository)
    before = git_output(root, "worktree", "list", "--porcelain")
    ready = runtime.validate(member, "member")
    evidence = ready["evidence"]
    assert isinstance(evidence, dict)
    ratchet = evidence["extensions"]["shard_details"]["test:check"]["ratchet"]
    assert ratchet["new_count"] == 0
    assert ratchet["baseline"] == lifecycle._recorded_base(member)
    assert git_output(root, "worktree", "list", "--porcelain") == before
    if runtime is lifecycle:
        graph, inputs = lifecycle._runtime_validation(
            lifecycle.load_manifest(member / "signetum.toml")
        )
        with pytest.raises(ValidationExecutionError):
            run_repository_gate(member, graph, "final", inputs, root.parent / "final-receipts")
    else:
        with pytest.raises(runtime.ValidationExecutionError):
            runtime._run_gate(member, "final", base=runtime._recorded_base(member))


@pytest.mark.parametrize("extra", [OLD, {**OLD, "message": "new problem"}])
def test_new_occurrence_or_changed_message_blocks_member(repository, extra, runtime):
    _, member, _ = configured(repository)
    commit_file(member, "diagnostics.json", document(OLD, extra))
    with pytest.raises(execution_failure(runtime), match="new diagnostics"):
        runtime.validate(member, "member")


def test_baseline_cache_reuses_only_completed_tool_bound_measurements(repository, runtime):
    _, member, state = configured(repository)
    runtime.validate(member, "member")
    runtime.validate(member, "member")
    runs = (state / "runs").read_text().splitlines()
    assert runs.count(str(member.resolve())) == 2
    assert len(runs) == 3


def test_current_unavailable_report_never_counts_as_no_findings(repository, runtime):
    _, member, _ = configured(repository)
    commit_file(member, "diagnostics.json", "not JSON")
    with pytest.raises(execution_failure(runtime), match="diagnostic"):
        runtime.validate(member, "member")


def test_unavailable_member_measurement_has_infrastructure_exit(repository, monkeypatch, capsys):
    _, member, _ = configured(repository)
    commit_file(member, "diagnostics.json", "not JSON")
    monkeypatch.chdir(member)
    assert lifecycle.main(["ready"]) == 4
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "infrastructure_error"
    assert "invalid diagnostic" in result["cause"]


def test_latest_supported_sync_source_replaces_the_old_ratchet_baseline(repository, runtime):
    root, member, _ = configured(repository)
    commit_file(root, "diagnostics.json", document())
    git_output(root, "push", "origin", "main")
    # A delivery fix which this member has not synchronized is not its baseline.
    runtime.validate(member, "member")
    with pytest.raises(MergeConflict):
        ops.workspace_sync(member)
    (member / "diagnostics.json").write_text(document(OLD))
    git_output(member, "add", "diagnostics.json")
    git_output(member, "commit", "--no-edit")
    assert "diagnostics.json" in member_contribution_paths(
        member, lifecycle._recorded_base(member), git_output(member, "rev-parse", "HEAD")
    )
    with pytest.raises(execution_failure(runtime), match="new diagnostics"):
        runtime.validate(member, "member")


def test_unavailable_baseline_is_explicit_and_is_not_cached(repository, runtime):
    _, member, state = configured(repository, baseline_report="not JSON")
    commit_file(member, "diagnostics.json", document())
    for _ in range(2):
        ready = runtime.validate(member, "member")
        evidence = ready["evidence"]
        assert isinstance(evidence, dict)
        assert evidence["extensions"]["shard_details"]["test:check"]["ratchet"][
            "baseline_unavailable"
        ]
    assert len((state / "runs").read_text().splitlines()) == 4


def test_unavailable_baseline_does_not_waive_current_findings(repository, runtime):
    _, member, _ = configured(repository, baseline_report="not JSON")
    with pytest.raises(execution_failure(runtime), match="new diagnostics"):
        runtime.validate(member, "member")


def test_tool_identity_change_invalidates_baseline_cache(repository, runtime):
    _, member, state = configured(repository)
    runtime.validate(member, "member")
    (state / "tool").write_text("v2")
    runtime.validate(member, "member")
    assert len((state / "runs").read_text().splitlines()) == 4


def test_admission_rechecks_the_ratchet_source_qualification(repository, runtime):
    root, member, _ = configured(repository)
    commit_file(root, "published.txt", "published source")
    git_output(root, "push", "origin", "main")
    ops.workspace_sync(member)
    runtime.validate(member, "member")
    tip = git_output(member, "rev-parse", "HEAD")
    assert admission(runtime, member, tip)
    for path in (lifecycle._state_root(member) / "synchronization").glob("*.json"):
        path.unlink()
    with pytest.raises(runtime.AdmissionError, match="no evidence"):
        admission(runtime, member, tip)
    runtime.validate(member, "member")
    assert admission(runtime, member, tip)


def test_unverified_merge_trailer_cannot_waive_a_new_finding(repository, runtime):
    root, member, _ = configured(repository)
    findings = document(OLD, {**OLD, "message": "new problem"})
    commit_file(member, "diagnostics.json", findings)
    sibling = root.parent / "unverified-source"
    git_output(root, "worktree", "add", "-b", "unverified", str(sibling), "HEAD")
    source = commit_file(sibling, "diagnostics.json", findings)
    git_output(member, "merge", "--no-ff", source, "-m", f"manual merge\n\nSignetum-Sync: {source}")
    with pytest.raises(execution_failure(runtime), match="new diagnostics"):
        runtime.validate(member, "member")


def test_archive_attributes_cannot_silently_remove_baseline_inputs(repository, runtime):
    root, _ = repository
    (root / ".gitattributes").write_text("diagnostics.json export-ignore\n")
    _, member, _ = configured(repository)
    commit_file(member, "diagnostics.json", document())
    ready = runtime.validate(member, "member")
    evidence = ready["evidence"]
    assert isinstance(evidence, dict)
    assert (
        "committed tree"
        in evidence["extensions"]["shard_details"]["test:check"]["ratchet"]["baseline_unavailable"]
    )


def test_ty_adapter_ignores_positions_but_retains_repeated_diagnostics(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.ty.src]\ninclude = ["module.py"]\n')
    source = tmp_path / "module.py"
    source.write_text("print(undefined_symbol)\n")
    first = diagnostic_multiset(ty_document(tmp_path))
    source.write_text("\n\nprint(undefined_symbol)\n")
    assert diagnostic_multiset(ty_document(tmp_path)) == first
    source.write_text("print(undefined_symbol)\nprint(undefined_symbol)\n")
    assert diagnostic_multiset(ty_document(tmp_path)) == first + first


def test_traceability_adapter_compares_real_git_inventories(repository):
    root, _ = repository
    decision = root / "docs/decisions/ADP-existing.md"
    decision.parent.mkdir(parents=True)
    decision.write_text(
        "# Existing\nStatus: Accepted\nSupersedes: ADP-missing.md\nSuperseded by: None\n"
    )
    manifest = root / "signetum.toml"
    strict = json.dumps(["signetum", "check", "traceability", "--repository", "."])
    report = json.dumps([sys.executable, "-m", "signetum.validation.diagnostics", "traceability"])
    manifest.write_text(
        manifest.read_text().replace(
            'name = "test:check"\ncommand = ["true"]',
            f'name = "test:check"\ncommand = {strict}\nratchet_command = {report}',
        )
    )
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "existing corpus issue")
    member = opened(root, "plan/corpus")
    commit_approval(member, "example")
    commit_file(member, "note.md")
    assert diagnostic_multiset(traceability_document(member)).total() > 0
    ready = lifecycle.validate(member, "member")
    evidence = ready["evidence"]
    assert isinstance(evidence, dict)
    details = evidence["extensions"]["shard_details"]["test:check"]["ratchet"]
    assert details["baseline_count"] == details["current_count"] > 0
    assert details["baseline_unavailable"] is None


@pytest.mark.parametrize(
    "raw",
    [
        {"schema_version": 2, "diagnostics": []},
        {"schema_version": True, "diagnostics": []},
        {"schema_version": 1, "diagnostics": [{**OLD, "file": "/outside.py"}]},
        {"schema_version": 1, "diagnostics": [{**OLD, "file": "../outside.py"}]},
        {"schema_version": 1, "diagnostics": [{**OLD, "line": True}]},
        {"schema_version": 1, "diagnostics": [{**OLD, "unsupported": "not a finding"}]},
    ],
)
def test_malformed_measurement_is_not_an_empty_finding_set(raw):
    with pytest.raises(ValidationInfrastructureError):
        diagnostic_multiset(json.dumps(raw))
