"""Structured whole-corpus checks compare against verified member baselines."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from change_fixtures import commit_approval
from signetum import lifecycle
from signetum import workspace_operations as ops
from signetum.git import git_output
from signetum.operations import AdmissionError, MergeConflict
from signetum.profiles.ty import ty_document
from signetum.resources.schemas import evidence_schema_digest
from signetum.synchronization import member_contribution_paths
from signetum.validation.diagnostic_protocol import diagnostic_multiset
from signetum.validation.diagnostics import traceability_document
from signetum.validation.execution import ValidationInfrastructureError
from signetum.validation.repository import run_repository_gate
from test_workspace_operations import commit_file, opened

OLD = {"file": "module.py", "rule": "old-rule", "message": "inherited problem", "line": 2}


def document(*diagnostics):
    return json.dumps({"schema_version": 1, "diagnostics": list(diagnostics)})


@pytest.fixture
def runtime():
    return lifecycle


def execution_failure(runtime):
    return runtime.ValidationExecutionError


def admission(runtime, member, tip):
    return runtime._admission_evidence(member, tip, runtime.load_manifest(member / "signetum.toml"))


def configured(repository, *, baseline_report=None, prepared=False):
    root, state = repository
    script = (
        "import json, sys\nfrom pathlib import Path\n"
        # Like a project environment, the report needs what preparation installs.
        + ("if not Path('.prepared').exists(): sys.exit(9)\n" if prepared else "")
        + f"log=Path({str(state / 'runs')!r})\n"
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
            "[signetum]",
            '[signetum]\nevidence_protocol = "reposeal.validation-evidence@3"\n'
            + f'evidence_schema_digest = "{evidence_schema_digest()}"\n',
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
    graph, inputs = runtime._runtime_validation(runtime.load_manifest(member / "signetum.toml"))
    runner = (
        run_repository_gate
        if runtime is lifecycle
        else importlib.import_module("signetum.validation.repository").run_repository_gate
    )
    with pytest.raises(runtime.ValidationExecutionError):
        runner(member, graph, "final", inputs, root.parent / "final-receipts")


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
    qualification = [path for path in runs if "/signetum-ready-" in path and path.endswith("/tree")]
    baseline = [path for path in runs if "/signetum-ratchet-" in path and path.endswith("/source")]
    assert len(runs) == 3
    assert len(qualification) == 2
    assert len(set(qualification)) == 2
    assert len(baseline) == 1
    assert str(member.resolve()) not in runs


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


def test_unavailable_baseline_fails_the_shard_and_is_not_cached(repository, runtime):
    _, member, state = configured(repository, baseline_report="not JSON")
    commit_file(member, "diagnostics.json", document())
    for _ in range(2):
        with pytest.raises(ValidationInfrastructureError, match="test:check") as failure:
            runtime.validate(member, "member")
        assert lifecycle._recorded_base(member) in str(failure.value)
    assert len((state / "runs").read_text().splitlines()) == 4


def test_baseline_is_measured_in_a_prepared_checkout(repository, runtime):
    root, _ = repository
    manifest = root / "signetum.toml"
    manifest.write_text(
        manifest.read_text().replace(
            "sys.exit(13 if (p/'fail').exists() else 0)",
            "Path('.prepared').write_text('installed'); sys.exit(13 if (p/'fail').exists() else 0)",
        )
    )
    (root / ".gitignore").write_text(".prepared\n")
    _, member, _ = configured(repository, prepared=True)
    ready = runtime.validate(member, "member")
    evidence = ready["evidence"]
    assert isinstance(evidence, dict)
    details = evidence["extensions"]["shard_details"]["test:check"]["ratchet"]
    assert details["baseline_count"] == 1
    assert details["new_count"] == 0


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
    source = git_output(root, "rev-parse", "HEAD")
    ops.workspace_sync(member)
    ready = runtime.validate(member, "member")
    evidence = ready["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["extensions"]["shard_details"]["test:check"]["ratchet"]["baseline"] == source
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
    merge = git_output(member, "rev-parse", "HEAD")
    with pytest.raises(execution_failure(runtime), match="new diagnostics") as failure:
        runtime.validate(member, "member")
    diagnostic = str(failure.value)
    assert f"baseline={lifecycle._recorded_base(member)}" in diagnostic
    recovery = diagnostic[diagnostic.index("new diagnostics") :]
    assert merge in recovery
    assert "maintenance workspace-sync " in recovery
    assert "maintenance workspace-sync --batch" in recovery


def observed_bases(repository):
    root, state = repository
    log = state / "bases"
    command = [
        sys.executable,
        "-c",
        "import json, pathlib, sys\n"
        "log, base, baseline, paths = sys.argv[1:]\n"
        "if paths:\n"
        "    document = json.loads(pathlib.Path(paths).read_text())\n"
        "    assert document['schema_version'] == 1\n"
        "    paths = document['paths']\n"
        "with open(log, 'a') as stream:\n"
        "    stream.write(json.dumps([base, baseline, paths]) + '\\n')\n",
        str(log),
        "{signetum.base}",
        "{signetum.ratchet_baseline}",
        "{signetum.contribution_paths_file}",
    ]
    manifest = root / "signetum.toml"
    manifest.write_text(
        manifest.read_text().replace(
            'name = "test:check"\ncommand = ["true"]',
            f'name = "test:check"\ncommand = {json.dumps(command)}',
        )
    )
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "observe shard bases")
    return lambda: json.loads(log.read_text().splitlines()[-1])


def test_member_shards_receive_bases_that_bind_their_receipt(repository):
    root, _ = repository
    last = observed_bases(repository)
    member = opened(root, "plan/bases")
    commit_approval(member, "example")
    commit_file(member, "work.txt")
    base = lifecycle._recorded_base(member)
    lifecycle.validate(member, "member")
    assert last()[:2] == [base, base]
    assert "work.txt" in last()[2]

    source = commit_file(root, "published.txt", "published source")
    git_output(root, "push", "origin", "main")
    ops.workspace_sync(member)
    lifecycle.validate(member, "member")
    assert last()[:2] == [base, source]
    paths = last()[2]
    assert "work.txt" in paths
    assert "published.txt" not in paths
    tip = git_output(member, "rev-parse", "HEAD")
    assert admission(lifecycle, member, tip)

    # Without the sync record the baseline returns to the recorded base, so
    # the receipt that observed the synchronized baseline no longer admits.
    for path in (lifecycle._state_root(member) / "synchronization").glob("*.json"):
        path.unlink()
    with pytest.raises(AdmissionError, match="no evidence"):
        admission(lifecycle, member, tip)
    lifecycle.validate(member, "member")
    assert last()[:2] == [base, base]
    assert admission(lifecycle, member, tip)

    graph, inputs = lifecycle._runtime_validation(lifecycle.load_manifest(member / "signetum.toml"))
    run_repository_gate(member, graph, "final", inputs, root.parent / "final-receipts")
    # The final gate has no range; declared range values are explicit empty arguments.
    assert last() == ["", "", ""]


PROBE = """import json, os, sys
from pathlib import Path
log, *values = sys.argv[1:]
engine = ("BASE", "RATCHET_BASELINE", "CONTRIBUTION_PATHS", "ADMISSION_BASE",
          "VALIDATION_WORKERS", "RECOVERY_REPORT", "SCHEDULE_FILE")
inherited = sorted(name for name in engine if "SIGNETUM_" + name in os.environ)
with open(log, "a") as stream:
    texts = [Path(value).read_text() if Path(value).is_file() else None for value in values]
    stream.write(json.dumps({"values": values, "texts": texts, "environment": inherited}) + "\\n")
"""


def test_engine_values_reach_a_runner_only_through_declared_placeholders(repository):
    root, state = repository
    declared, plain = state / "declared", state / "plain"
    (root / "probe.py").write_text(PROBE)
    (root / "weights.json").write_text('{"tests/test_example.py::test_example": 3}')
    check = [
        sys.executable,
        "probe.py",
        str(declared),
        "{signetum.validation_workers}",
        "{signetum.schedule_file}",
        "{signetum.recovery_report_file}",
        "{signetum.admission_base}",
    ]
    manifest = root / "signetum.toml"
    text = manifest.read_text()
    text = text.replace("[validation]\n", '[validation]\nschedule_file = "weights.json"\n')
    text = text.replace(
        'changes = "changes"\n', 'changes = "changes"\nlockfiles = ["weights.json"]\n'
    )
    text = text.replace(
        'name = "test:check"\ncommand = ["true"]',
        f'name = "test:check"\ncommand = {json.dumps(check)}\n'
        '[[validation.shards]]\nname = "test:plain"\n'
        f"command = {json.dumps([sys.executable, 'probe.py', str(plain), 'literal'])}",
    )
    text = text.replace(
        'name = "member"\nshards = ["test:check"]',
        'name = "member"\nshards = ["test:check", "test:plain"]',
    )
    manifest.write_text(text)
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare engine values")
    member = opened(root, "plan/values")
    commit_approval(member, "example")
    commit_file(member, "work.txt")

    lifecycle.validate(member, "member")

    observed = json.loads(declared.read_text().splitlines()[-1])
    workers, schedule, recovery, admission_base = observed["values"]
    assert workers.isdecimal()
    assert Path(schedule).is_absolute() and Path(schedule).name == "weights.json"
    assert observed["texts"][1] == (root / "weights.json").read_text()
    assert Path(recovery).is_absolute()
    # The batch increment does not exist in a member gate; the declared value is empty.
    assert admission_base == ""
    # An undeclared value is never substituted or supplied through the environment.
    assert json.loads(plain.read_text().splitlines()[-1]) == {
        "values": ["literal"],
        "texts": [None],
        "environment": [],
    }
    assert observed["environment"] == []


def test_archive_attributes_cannot_silently_remove_baseline_inputs(repository, runtime):
    root, _ = repository
    (root / ".gitattributes").write_text("diagnostics.json export-ignore\n")
    _, member, _ = configured(repository)
    commit_file(member, "diagnostics.json", document())
    with pytest.raises(ValidationInfrastructureError, match="committed tree"):
        runtime.validate(member, "member")


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
