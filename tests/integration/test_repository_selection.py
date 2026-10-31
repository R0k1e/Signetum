"""A repository supplies selection; the existing gate owns execution and proof."""

import importlib
import json
import sys
import tomllib
from importlib.resources import files
from pathlib import Path

import pytest
from change_fixtures import consolidated_approval
from jsonschema import Draft202012Validator
from signetum.git import git_output
from signetum.resources import schemas
from signetum.validation import process_observation


@pytest.fixture
def selection_runtime(request, monkeypatch):
    return importlib.import_module("signetum.repository_selection")


def declare_provider(root, *, mode="valid"):
    tests = root / "tests"
    tests.mkdir()
    (tests / "__init__.py").touch()
    (root / ".gitignore").write_text("__pycache__/\n.selection-note\n")
    (root / "source.py").write_text("def doubled(value): return value * 2\n")
    for name in ("a", "b"):
        (tests / f"test_{name}.py").write_text(
            "import unittest\nfrom source import doubled\n"
            "class Result(unittest.TestCase):\n"
            "    def test_result(self): self.assertEqual(doubled(2), 4)\n"
        )
    (root / "rules.json").write_text(json.dumps(dict(mode=mode)))
    (root / "selector.py").write_text("""import json,sys
from pathlib import Path
q=json.load(sys.stdin)
mode=json.loads(Path("rules.json").read_text())["mode"]
if mode=="failure": sys.exit(9)
if mode=="malformed": print("not json"); sys.exit(0)
if mode=="mutate": Path("seed.txt").write_text("modified by provider")
if mode=="change-tool": Path(".tool-id").write_text("tool-v2")
if mode=="leak":
    import subprocess
    child=subprocess.Popen(
        [sys.executable,"-c","import time;time.sleep(30)"],start_new_session=True)
    (Path.cwd().parent/"selection-leaked-pid").write_text(str(child.pid))
name="missing:check" if mode=="unknown" else "test:check"
coverage=[dict(path=p,status="unexplained" if mode=="unexplained" else "covered",
               shards=[] if mode=="unexplained" else [name],reason="Repository rule.")
          for p in q["files"]]
if mode=="missing-path": coverage=coverage[1:]
if mode=="duplicate": coverage=coverage+coverage[:1]
if mode=="unstable":
    note=Path(".selection-note")
    for item in coverage: item["reason"]=note.read_text() if note.exists() else "Initial proof."
path="tests/test_b.py" if mode=="omit-test" else "tests/test_a.py"
if mode=="escape": path="../secret"
argument="tests/test_b.py" if mode=="misbound" else path
if mode=="narrow-modified": argument=path+"::Result::test_result"
if mode=="empty":
    for item in coverage: item["shards"]=[]
if mode=="docs-aware":
    for item in coverage:
        if item["path"].startswith(("docs/", "changes/")): item["shards"]=[]
digest="sha256:"+"0"*64 if mode=="stale" else q["request_digest"]
plans=[dict(shard="test:check",tests=[dict(path=path,argument=argument)])]
if mode=="whole-shard" or not any(item["shards"] for item in coverage): plans=[]
print(json.dumps(dict(protocol="signetum.selection@1",request_digest=digest,
                     coverage=coverage,targets=plans)))
""")
    manifest = root / "signetum.toml"
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
    text = manifest.read_text().replace('["true"]', json.dumps(command))
    text += '\n[impact.provider]\nprotocol="signetum.selection@1"\nentrypoint="selector.py"\n'
    text += "command=" + json.dumps([sys.executable, "{selector}"]) + "\n"
    text += 'inputs=["rules.json"]\n'
    text += (
        'tools=[{name="selector-python",identity_command='
        + json.dumps([sys.executable, "--version"])
        + "}]\n"
    )
    text += '[[impact.provider.targets]]\nshard="test:check"\nroots=["tests"]\nargument_index=3\n'
    if mode == "whole-shard":
        text = text.split("[[impact.provider.targets]]")[0]
    manifest.write_text(text)
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare repository selection authority")
    return git_output(root, "rev-parse", "HEAD")


def resolve(root, runtime, files=("source.py",)):
    source = git_output(root, "rev-parse", "HEAD")
    loader = importlib.import_module(runtime.__package__ + ".manifest").load_manifest
    manifest = loader(root / "signetum.toml")
    return runtime.select_repository(root, manifest, files, base=source, source=source)


def test_structured_selection_refines_only_the_declared_test_argument_tail(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root)
    result = resolve(root, selection_runtime)
    shard = next(s for s in result.manifest.validation.shards if s.name == "test:check")
    assert shard.command == (sys.executable, "-m", "unittest", "tests/test_a.py")
    assert result.selection.shards == ("test:check",)
    assert not result.selection.unexplained
    assert not git_output(root, "status", "--porcelain")
    # Runners may use implicit full-suite discovery, with no positional tail.
    manifest = root / "signetum.toml"
    manifest.write_text(
        manifest.read_text().replace(
            json.dumps([sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
            json.dumps([sys.executable, "-m", "unittest"]),
        )
    )
    git_output(root, "commit", "-am", "bind an implicit discovery runner")
    implicit = resolve(root, selection_runtime)
    assert (
        next(s for s in implicit.manifest.validation.shards if s.name == "test:check").command
        == shard.command
    )


@pytest.mark.parametrize(
    "mode", ["unknown", "missing-path", "duplicate", "escape", "stale", "malformed"]
)
def test_invalid_selection_never_produces_a_resolved_execution_plan(
    local_repository, selection_runtime, mode
):
    root, _ = local_repository
    declare_provider(root, mode=mode)
    with pytest.raises(selection_runtime.SelectionError):
        resolve(root, selection_runtime)
    assert not git_output(root, "status", "--porcelain")


def test_unexplained_paths_retain_the_full_declared_command(local_repository, selection_runtime):
    root, _ = local_repository
    declare_provider(root, mode="unexplained")
    result = resolve(root, selection_runtime)
    shard = next(s for s in result.manifest.validation.shards if s.name == "test:check")
    assert shard.command == (sys.executable, "-m", "unittest", "discover", "-s", "tests")
    assert result.selection.unexplained == ("source.py",)
    assert result.selection.requires_final


def test_changed_tests_cannot_be_lost_by_narrowing_to_other_targets(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root, mode="omit-test")
    with pytest.raises(selection_runtime.SelectionError, match="modified test"):
        resolve(root, selection_runtime, ("tests/test_a.py",))


@pytest.mark.parametrize("selection_runtime", ["engine"], indirect=True)
def test_provider_failure_is_infrastructure_without_running_validation(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root, mode="failure")
    with pytest.raises(selection_runtime.InfrastructureError):
        resolve(root, selection_runtime)


def test_selection_implementation_and_rules_are_validation_identity_inputs(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root)
    result = resolve(root, selection_runtime)
    _, inputs = selection_runtime.configured_validation(
        result.manifest, catalog=selection_runtime.builtin_catalog()
    )
    assert {"selector.py", "rules.json"} <= set(inputs.lockfiles)
    assert "selector-python" in {tool.name for tool in inputs.tools}


def _selected_member(repository, selection_runtime, *, mode="valid", broken_full=False):
    root, _ = repository
    declare_provider(root, mode=mode)
    manifest = root / "signetum.toml"
    text = manifest.read_text().replace(
        'name = "batch"\nshards = ["test:check"]', 'name = "batch"\nshards = []'
    )
    if mode == "docs-aware":
        text = text.replace('paths = ["**"]', 'paths = ["source.py", "tests/**"]')
        text = text.replace(
            'name = "test:check"\ncommand', 'name = "test:check"\ninherit = true\ncommand'
        )
    if mode == "docs-aware":
        text += (
            '\n[[impact.rules]]\nname="documentation"\npaths=["docs/**","changes/**"]\nshards=[]\n'
        )
    manifest.write_text(text)
    if broken_full:
        test = root / "tests/test_b.py"
        test.write_text(test.read_text().replace("doubled(2), 4", "doubled(2), 9"))
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "bind complete and selective validation boundaries")
    git_output(root, "push", "origin", "main")
    base = git_output(root, "rev-parse", "HEAD")
    runtime = importlib.import_module(selection_runtime.__package__ + ".lifecycle")
    opened = runtime.workspace_open(root, "plan/selected", base)
    member = Path(opened["worktree"])
    consolidated_approval(member, base)
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "approve selected validation fixture")
    (member / "source.py").write_text("def doubled(value): return value + value\n")
    git_output(member, "commit", "-am", "implement the same observable outcome")
    return runtime, root, member, base


@pytest.mark.parametrize("selection_runtime", ["engine"], indirect=True)
def test_real_member_diagnostics_ready_admission_and_full_final_share_selection(
    repository, selection_runtime
):
    runtime, root, member, base = _selected_member(repository, selection_runtime)
    changed = runtime.changed(member, True)
    assert changed["selection"]["shards"] == ["test:check"]
    ready = runtime.validate(member, "member")
    assert ready["status"] == "ready"
    assert ready["evidence"]["selection"] == changed["selection"]
    batch = Path(runtime.batch_open(root, (member,))["batch"])
    final = runtime.validate(batch, "final")
    command_digest = importlib.import_module(
        selection_runtime.__package__ + ".validation"
    ).command_digest
    full = (sys.executable, "-m", "unittest", "discover", "-s", "tests")
    assert final["evidence"]["execution"]["shards"][0]["command_digest"] == command_digest(full)
    assert git_output(root, "rev-parse", "main") == base


def test_final_cannot_inherit_a_members_narrow_target_list(repository, selection_runtime):
    runtime, root, member, base = _selected_member(repository, selection_runtime, broken_full=True)
    assert runtime.validate(member, "member")["status"] == "ready"
    batch = Path(runtime.batch_open(root, (member,))["batch"])
    with pytest.raises(runtime.ValidationExecutionError):
        runtime.validate(batch, "final")
    assert not list(runtime._receipt_root(batch).glob("final-lifecycle-*.json"))
    assert git_output(root, "rev-parse", "main") == base


def test_provider_nonselecting_fixup_can_inherit_exact_test_evidence(repository, selection_runtime):
    runtime, _, member, _ = _selected_member(repository, selection_runtime, mode="docs-aware")
    first = runtime.validate(member, "member")
    doc = member / "docs/note.md"
    doc.parent.mkdir(exist_ok=True)
    doc.write_text("A nonselecting clarification.\n")
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "clarify documentation without changing tests")
    second = runtime.validate(member, "member")
    inherited = second["evidence"]["extensions"]["inherited_test_evidence_from"]
    assert inherited["commit"] == first["source"]
    assert inherited["shards"] == ["test:check"]


def test_selected_source_identity_cannot_name_a_different_executed_file(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root, mode="misbound")
    with pytest.raises(selection_runtime.SelectionError, match="argument"):
        resolve(root, selection_runtime)


def test_modifying_a_test_file_requires_the_whole_file_not_one_named_node(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root, mode="narrow-modified")
    with pytest.raises(selection_runtime.SelectionError, match="modified test"):
        resolve(root, selection_runtime, ("tests/test_a.py",))


def test_unknown_paths_cannot_be_marked_covered_without_any_check(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root, mode="empty")
    manifest = root / "signetum.toml"
    manifest.write_text(manifest.read_text().replace('paths = ["**"]', 'paths = ["known/**"]'))
    git_output(root, "commit", "-am", "retain an unexplained source boundary")
    with pytest.raises(selection_runtime.SelectionError, match="explicit impact rule"):
        resolve(root, selection_runtime)


def test_adoption_declarations_match_the_shipped_manifest_schema(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root)
    manifest = root / "signetum.toml"
    raw = tomllib.loads(manifest.read_text())
    model = importlib.import_module(selection_runtime.__package__ + ".manifest").load_manifest(
        manifest
    )
    raw["signetum"]["evidence_protocol"] = model.signetum.evidence_protocol
    raw["signetum"]["evidence_schema_digest"] = model.signetum.evidence_schema_digest
    schema = json.loads((files(schemas) / "signetum-v4.schema.json").read_text())
    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors(raw)) == []
    raw["impact"]["provider"]["protocol"] = "invented@99"
    assert list(validator.iter_errors(raw))


def test_provider_cannot_mutate_source_to_make_its_selection_true(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root, mode="mutate")
    with pytest.raises(selection_runtime.SelectionError, match="changed"):
        resolve(root, selection_runtime)
    assert (root / "seed.txt").read_text() == "modified by provider"
    assert git_output(root, "status", "--porcelain")


def test_selection_rechecks_tool_identity_before_accepting_a_plan(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root, mode="change-tool")
    ignore = root / ".gitignore"
    ignore.write_text(ignore.read_text() + ".tool-id\n")
    (root / ".tool-id").write_text("tool-v1")
    manifest = root / "signetum.toml"
    identity = [
        sys.executable,
        "-c",
        "from pathlib import Path;print(Path('.tool-id').read_text())",
    ]
    manifest.write_text(
        manifest.read_text().replace(
            json.dumps([sys.executable, "--version"]), json.dumps(identity)
        )
    )
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare an observable mutable tool identity")
    with pytest.raises(selection_runtime.SelectionError, match="tool identities"):
        resolve(root, selection_runtime)
    assert not git_output(root, "status", "--porcelain")
    assert resolve(root, selection_runtime).selection.shards == ("test:check",)


@pytest.mark.parametrize("selection_runtime", ["engine"], indirect=True)
def test_provider_process_leak_refuses_a_plan_and_settles_its_owned_child(
    local_repository, selection_runtime
):
    root, _ = local_repository
    declare_provider(root, mode="leak")
    with pytest.raises(selection_runtime.InfrastructureError, match="owned process leak"):
        resolve(root, selection_runtime)
    pid = int((root.parent / "selection-leaked-pid").read_text())
    try:
        identity = process_observation.process_identity(pid)
    except OSError:
        pass
    else:
        assert identity.zombie


def test_admission_recomputes_selection_proof_even_when_the_commands_are_unchanged(
    repository, selection_runtime
):
    runtime, root, member, base = _selected_member(repository, selection_runtime, mode="unstable")
    ready = runtime.validate(member, "member")
    (member / ".selection-note").write_text("A changed producer proof.")
    assert git_output(member, "rev-parse", "HEAD") == ready["source"]
    assert not git_output(member, "status", "--porcelain")
    with pytest.raises(runtime.AdmissionError, match="no evidence"):
        runtime.batch_open(root, (member,))
    assert git_output(root, "rev-parse", "main") == base


def test_open_merge_runs_only_batch_static_and_final_retains_complete_checks(
    repository, selection_runtime
):
    runtime, root, first, base = _selected_member(repository, selection_runtime, broken_full=True)
    assert runtime.validate(first, "member")["status"] == "ready"
    second = Path(runtime.workspace_open(root, "plan/other", base)["worktree"])
    record = consolidated_approval(second, base)
    record.write_text(record.read_text().replace('id = "example"', 'id = "other"'))
    record.parent.rename(record.parent.with_name("other"))
    git_output(second, "add", ".")
    git_output(second, "commit", "-m", "approve another independent member")
    (second / "source.py").write_text("def doubled(value): return 2 * value\n")
    git_output(second, "commit", "-am", "implement the second approved outcome")
    assert runtime.validate(second, "member")["status"] == "ready"
    batch = Path(runtime.batch_open(root, (first,))["batch"])
    with pytest.raises(runtime.MergeConflict):
        runtime.admit(batch, (second,))
    (batch / "source.py").write_text("def doubled(value): return sum((value, value))\n")
    git_output(batch, "add", "source.py")
    continued = runtime.continue_batch(batch)
    assert continued["status"] == "continued"
    assert continued["static"]["executed"] == []
    assert git_output(batch, "rev-parse", "--verify", "MERGE_HEAD", check=False) == ""
    with pytest.raises(runtime.ValidationExecutionError):
        runtime.validate(batch, "final")
    assert git_output(root, "rev-parse", "main") == base


def test_whole_shard_provider_needs_no_file_refinement_binding_for_changed_tests(
    repository, selection_runtime
):
    runtime, root, member, base = _selected_member(
        repository, selection_runtime, mode="whole-shard"
    )
    test = member / "tests/test_a.py"
    test.write_text(test.read_text() + "# A modified test must run through the full shard.\n")
    git_output(member, "commit", "-am", "refine a test without file-target support")
    ready = runtime.validate(member, "member")
    assert ready["status"] == "ready"
    assert ready["evidence"]["selection"]["modified_tests"] == ["tests/test_a.py"]
    command_digest = importlib.import_module(
        selection_runtime.__package__ + ".validation"
    ).command_digest
    full = (sys.executable, "-m", "unittest", "discover", "-s", "tests")
    assert ready["evidence"]["execution"]["shards"][0]["command_digest"] == command_digest(full)
    assert runtime.batch_open(root, (member,))["admitted"]
    assert git_output(root, "rev-parse", "main") == base


@pytest.mark.parametrize("selection_runtime", ["engine"], indirect=True)
def test_without_provider_executes_full_member_checks_despite_no_check_impact_rules(
    repository, selection_runtime
):
    runtime, root, member, base = _selected_member(repository, selection_runtime, mode="docs-aware")
    manifest = member / "signetum.toml"
    text = manifest.read_text().split("[impact.provider]")[0]
    text = text.replace('shards = ["test:check"]', "shards = []", 1)
    manifest.write_text(text)
    git_output(member, "commit", "-am", "use full default validation")
    changed = runtime.changed(member, True)
    assert changed["executed"] == []
    assert changed["shards"] == ("test:check",)
    first = runtime.validate(member, "member")
    note = member / "docs/note.md"
    note.parent.mkdir(exist_ok=True)
    note.write_text("A documentation-only fixup still executes the full default.\n")
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "clarify full default")
    second = runtime.validate(member, "member")
    assert second["source"] != first["source"]
    assert "inherited_test_evidence_from" not in second["evidence"]["extensions"]
    batch = Path(runtime.batch_open(root, (member,))["batch"])
    assert runtime.validate(batch, "final")["status"] == "final"
    assert git_output(root, "rev-parse", "main") == base
    # A defect in the test previously omitted by the producer must fail the default.
    test = member / "tests/test_b.py"
    test.write_text(test.read_text().replace("doubled(2), 4", "doubled(2), 99"))
    git_output(member, "commit", "-am", "expose full default coverage")
    assert runtime.changed(member, False)["checks_started"] is False
    with pytest.raises(runtime.ValidationExecutionError, match="test:check"):
        runtime.validate(member, "member")
    with pytest.raises(runtime.ValidationExecutionError, match="test:check"):
        runtime.validate(member, "member")
    with pytest.raises(runtime.AdmissionError):
        runtime._admission_evidence(
            member,
            git_output(member, "rev-parse", "HEAD"),
            runtime.load_manifest(member / "signetum.toml"),
        )
