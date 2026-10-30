import json
import shlex
import subprocess
import sys
from pathlib import Path
from shutil import which
from zipfile import ZipFile

import yaml
from change_fixtures import approve_change
from test_batch_admission import MANIFEST
from test_repository_selection import declare_provider

from signetum.change_record import contract_digest, parse_change_record
from signetum.git import git_output
from signetum.manifest import load_manifest
from signetum.runtime_generation import RUNTIME_DIRECTORY, runtime_files
from signetum.template import render_template
from signetum.validation.repository import configured_validation
from signetum.workspaces import WorkspaceRecord, state_root, write_record


def test_built_wheel_ships_its_declared_resources_without_build_machine_facts() -> None:
    wheels = tuple(Path("dist").glob("signetum-*.whl"))
    assert len(wheels) == 1

    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        payload = "\n".join(
            wheel.read(name).decode("utf-8", errors="replace")
            for name in names
            if name.endswith((".py", ".toml", ".json"))
        )

    assert "signetum/resources/schemas/signetum-v3.schema.json" in names
    assert "signetum/resources/profiles/python-default-v1.toml" in names
    assert "signetum/resources/schemas/validation-graph-v2.schema.json" in names
    assert "signetum/resources/schemas/validation-evidence-v3.schema.json" in names
    assert "signetum/resources/schemas/contracts/release-metadata.schema.json" in names
    assert "signetum/resources/skills/signetum/SKILL.md" in names
    assert "signetum/resources/vectors/validation-evidence-v3.json" in names
    # Absence is the contract here, so each value is bound to the reason it
    # must not appear rather than left as a bare literal nobody can extend.
    unrendered_template_placeholder = "placeholder_name"
    build_machine_home = str(Path.home())

    assert unrendered_template_placeholder not in payload
    assert build_machine_home not in payload


def test_installed_wheel_generates_the_same_portable_runtime(tmp_path, installed_python):
    python = installed_python
    output = tmp_path / "template"
    subprocess.run(  # noqa: S603 -- successful immutable payload; generated output belongs to this test
        [str(python), "-B", "-I", "-m", "signetum.runtime_generation", str(output)],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    runtime = output / RUNTIME_DIRECTORY
    actual = {
        path.relative_to(runtime).as_posix(): path.read_bytes()
        for path in runtime.rglob("*")
        if path.is_file()
    }
    assert actual == runtime_files()
    manifest_path = tmp_path / "signetum.toml"
    source_manifest = Path(__file__).parents[2] / "template/signetum.toml"
    manifest_path.write_bytes(source_manifest.read_bytes())
    catalog_probe = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from _signetum_runtime.test_scheduling import partition_units
from _signetum_runtime.python_selection import PythonSelection,dependent_units
from _signetum_runtime.ci_partitions import combine
assert partition_units(('a','b'),2,{}) == (('a',),('b',))
cfg=PythonSelection(schema_version=1,source_roots=('app',),unit_roots=('tests',),unit_shard='unit')
selected,_=dependent_units({'app/x.py':b'value=1','tests/test_x.py':b'import x'},('app/x.py',),cfg)
assert selected == ('tests/test_x.py',)
from _signetum_runtime.profile_catalog import load_catalog,resolve_profiles
from _signetum_runtime.manifest import load_manifest
from _signetum_runtime.configuration import configured_validation
root=Path(sys.argv[1])/'_signetum_runtime/profile_resources'
catalog=load_catalog(lambda name:(root/name).read_text(encoding='utf-8'))
resolved=resolve_profiles(('python-default@1','git-worktrunk@1'),catalog=catalog)
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules
manifest=load_manifest(Path(sys.argv[2]))
graph,inputs=configured_validation(manifest,catalog=catalog)
print(json.dumps({'identities':[item.identity for item in resolved],
                  'graph':graph.digest,'schema':inputs.schema_digest,'profiles':list(inputs.profiles)}))
"""
    result = subprocess.run(  # noqa: S603 -- isolated installed output, no engine/site packages
        [
            str(python),
            "-B",
            "-I",
            "-S",
            "-c",
            catalog_probe,
            str(runtime.parent),
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    graph, inputs = configured_validation(load_manifest(source_manifest))
    assert json.loads(result.stdout) == {
        "identities": ["shared-core@1", "python-default@1", "git-worktrunk@1"],
        "graph": graph.digest,
        "schema": inputs.schema_digest,
        "profiles": list(inputs.profiles),
    }

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    git_output(consumer, "init", "-b", "plan/installed")
    git_output(consumer, "config", "user.name", "Artifact test")
    git_output(consumer, "config", "user.email", "artifact@example.invalid")
    (consumer / "signetum.toml").write_text(MANIFEST)
    (consumer / "seed.txt").write_text("base")
    git_output(consumer, "add", ".")
    git_output(consumer, "commit", "-m", "declare installed consumer")
    consumer_base = git_output(consumer, "rev-parse", "HEAD")
    approve_change(consumer)
    git_output(consumer, "add", ".")
    git_output(consumer, "commit", "-m", "approve installed consumer change")
    (consumer / "implementation.txt").write_text("own implementation")
    git_output(consumer, "add", ".")
    git_output(consumer, "commit", "-m", "implement installed change")
    authority_probe = """
import io,json,sys
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from _signetum_runtime.traceability_cli import query
from _signetum_runtime.traceability_boundary import TraceabilityManifest
from _signetum_runtime.status_models import EvidenceSnapshot
from _signetum_runtime.development_store import main,snapshot
from _signetum_runtime.workspaces import WorkspaceRecord,state_root,write_record
root=Path(sys.argv[2])
write_record(state_root(root),WorkspaceRecord(1,'plan/installed',sys.argv[3],'member'))
output,errors=io.StringIO(),io.StringIO()
status=query(root,TraceabilityManifest(schema_version=1),EvidenceSnapshot(),output,errors)
assert status==0,errors.getvalue()
assert json.loads(output.getvalue())['valid'] is True
commands=[
 ['record','--change','example','--id','installed','--summary','Installed authority',
  '--requirement','REQ-1','--reason','Preserve installed source evidence'],
 ['resolve','--change','example','--id','installed-resolution',
  '--target','example/installed/observation','--reason','Existing behavior is sufficient',
  '--evidence','implementation.txt'],
 ['status'],
]
for command in commands:
 stream=io.StringIO()
 with redirect_stdout(stream):
  status=main([*command,'--repository',str(root)])
 assert status==0,stream.getvalue()
assert len(snapshot(root).observations)==1
assert snapshot(root).observations[0].status=='resolved'
from _signetum_runtime.configuration import configured_validation
from _signetum_runtime.profile_catalog import load_catalog
from _signetum_runtime.manifest import load_manifest
from _signetum_runtime.git import git_output
from _signetum_runtime.lifecycle_validation import validate_workspace
from _signetum_runtime.execution import ShardExecution
from _signetum_runtime.process import run_command
from _signetum_runtime.workspaces import WorkspaceRecord,state_root,write_record
git_output(root,'add','changes/example/events.jsonl')
git_output(root,'commit','-m','retain installed journal evidence')
catalog_root=Path(sys.argv[1])/'_signetum_runtime/profile_resources'
catalog=load_catalog(lambda name:(catalog_root/name).read_text())
def configure(manifest,*,member_shards=None):
 return configured_validation(manifest,catalog=catalog,member_shards=member_shards)
class NativeAdapter:
 def __init__(self,repository,*,member_base=None): self.repository=repository
 def commit_identity(self): return git_output(self.repository,'rev-parse','HEAD')
 def tree_identity(self): return git_output(self.repository,'rev-parse','HEAD^{tree}')
 def read_file(self,path): return (self.repository/path).read_bytes()
 def identify_tool(self,tool): raise AssertionError('unexpected undeclared tool')
 def report_findings(self,shard): raise AssertionError('unexpected world check')
 def run_shard(self,shard):
  completed=run_command(self.repository,shard.command,timeout_seconds=shard.timeout_seconds)
  return ShardExecution(completed.returncode==0,completed.stdout+completed.stderr)
def receipt_root(repository):
 path=state_root(repository)/'validation'
 path.mkdir(parents=True,exist_ok=True)
 return path
result=validate_workspace(root,'member',configure=configure,adapter_factory=NativeAdapter,
 receipt_root=receipt_root,proposal_paths=lambda repository:(),
 check_numbering_base=lambda *args:None)
assert result['status']=='ready'
assert result['evidence']['identity']['commit']==git_output(root,'rev-parse','HEAD')
assert Path(result['receipt']).is_file()
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules
"""
    result = subprocess.run(  # noqa: S603 -- actual installed generation, isolated native consumer
        [
            str(python),
            "-I",
            "-S",
            "-c",
            authority_probe,
            str(runtime.parent),
            str(consumer),
            consumer_base,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_installed_skill_routes_to_existing_repository_commands_and_generates_one_draft(tmp_path):
    wheels = tuple(Path("dist").glob("signetum-*.whl"))
    assert len(wheels) == 1
    installed = tmp_path / "installed skills/signetum"
    prefix = "signetum/resources/skills/signetum/"
    with ZipFile(wheels[0]) as wheel:
        for name in wheel.namelist():
            if name.startswith(prefix) and not name.endswith("/"):
                target = installed / name.removeprefix(prefix)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(wheel.read(name))
    assert (installed / "SKILL.md").is_file()
    interface = yaml.safe_load((installed / "agents/openai.yaml").read_text())["interface"]
    assert interface["display_name"] == "Signetum"
    assert "$signetum" in interface["default_prompt"]
    consumer = tmp_path / "existing repository"
    render_template(Path(__file__).parents[2] / "template", consumer)
    # This existing consumer binds its own host runner; the skill must preserve it.
    interpreter = shlex.quote(sys.executable)
    protocol = shlex.quote(str(consumer / ".agents/repo-dev/runtime/protocol.py"))
    (consumer / "Justfile").write_text(
        "set positional-arguments\nprotocol *args:\n    "
        + interpreter
        + " -I -S "
        + protocol
        + ' "$@"\n'
    )
    git_output(consumer, "init", "-b", "plan/consumer")
    git_output(consumer, "config", "user.name", "Skill consumer")
    git_output(consumer, "config", "user.email", "skill@example.invalid")
    git_output(consumer, "add", ".")
    git_output(consumer, "commit", "-m", "existing repository authority")
    base = git_output(consumer, "rev-parse", "HEAD")
    write_record(state_root(consumer), WorkspaceRecord(1, "plan/consumer", base, "member"))
    launcher = installed / "scripts/signetum"
    shell = which("sh")
    assert shell is not None
    just = which("just")
    assert just is not None
    for command in (("current",), ("change-open", "adopted-change")):
        result = subprocess.run(  # noqa: S603 -- installed skill, existing runner and temporary repo
            [shell, str(launcher), *command],
            cwd=consumer,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    record = consumer / "changes/adopted-change/change.toml"
    assert parse_change_record(record.read_text()).approval is None
    viewed = subprocess.run(  # noqa: S603 -- actual installed launcher preserves paths with spaces
        [shell, str(launcher), "view", str(record)],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert viewed.returncode == 0, viewed.stderr
    assert json.loads(viewed.stdout)["status"] == "proposal"
    assert len(list(record.parent.iterdir())) == 1
    source = record.read_text().replace("TODO", "Fixture owner confirmed:")
    digest = contract_digest(parse_change_record(source).contract)
    record.write_text(
        source
        + f'''[change.approval]
actor = "Fixture owner"
recorded_at = 2026-10-29
source = "The fixture owner confirms this isolated utility test."
contract_digest = "{digest}"
'''
    )
    git_output(consumer, "add", "changes")
    git_output(consumer, "commit", "-m", "confirm isolated utility contract")
    current = subprocess.run(  # noqa: S603 -- installed skill reads the current history identity
        [shell, str(launcher), "current"],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert current.returncode == 0, current.stderr
    history = json.loads(current.stdout)["history_digest"]
    request_path = tmp_path / "request with spaces.json"
    transaction = {
        "id": "adopted-change/observe",
        "change_id": "adopted-change",
        "approval_digest": digest,
        "operation": "record",
        "reason": "Retain the existing command owner.",
        "observations": [
            {
                "id": "adopted-change/finding",
                "requirements": ["REQ-001"],
                "summary": "The consumer owns the runner.",
                "reason": "Avoid creating a duplicate runner.",
            }
        ],
    }
    for operation in ("record", "resolve"):
        if operation == "resolve":
            transaction = {
                **transaction,
                "id": "adopted-change/answer",
                "operation": "resolve",
                "observations": [],
                "resolutions": [
                    {
                        "id": "adopted-change/disposition",
                        "target": "adopted-change/finding",
                        "status": "rejected",
                        "reason": "Existing binding already covers this need.",
                    }
                ],
            }
        request_path.write_text(json.dumps(transaction))
        result = subprocess.run(  # noqa: S603 -- installed mutations bind literal request paths and CAS
            [
                shell,
                str(launcher),
                operation,
                "--request",
                str(request_path),
                "--expected-history",
                history,
            ],
            cwd=consumer,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        history = json.loads(result.stdout)["history_digest"]
    status = subprocess.run(  # noqa: S603 -- standing answer is observed through the installed utility
        [shell, str(launcher), "status"],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["observations"][0]["status"] == "rejected"
    retained = subprocess.run(  # noqa: S603 -- original rationale remains independently retrievable
        [shell, str(launcher), "history", "--change", "adopted-change"],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert retained.returncode == 0, retained.stderr
    assert len(json.loads(retained.stdout)["entries"]) == 2
    assert sorted(path.name for path in record.parent.iterdir()) == ["change.toml", "events.jsonl"]
    # Native options survive Just and the installed shell launcher unchanged.
    observed = tmp_path / "diagnostic-arguments.json"
    command = [
        sys.executable,
        "-c",
        "import json,sys; from pathlib import Path; "
        f"Path({str(observed)!r}).write_text(json.dumps(sys.argv[1:]))",
    ]
    manifest = consumer / "signetum.toml"
    manifest.write_text(
        manifest.read_text()
        + '\n[[validation.shards]]\nname="repo:diagnostic"\ncommand='
        + json.dumps(command)
        + "\n"
    )
    feedback = subprocess.run(  # noqa: S603 -- installed launcher must retain the native option boundary
        [
            shell,
            str(launcher),
            "test",
            "--shard",
            "repo:diagnostic",
            "--",
            "--literal",
            "argument with spaces",
        ],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert feedback.returncode == 0, feedback.stdout + feedback.stderr
    assert json.loads(feedback.stdout)["outcome"] == "diagnostic"
    assert json.loads(observed.read_text()) == ["--literal", "argument with spaces"]

    sentinel = consumer / "must-not-run"
    refused = subprocess.run(  # noqa: S603 -- shell syntax is a literal invalid utility argument
        [shell, str(launcher), "change-open", "$(touch must-not-run)"],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert not sentinel.exists()

    unadopted = tmp_path / "unadopted"
    unadopted.mkdir()
    existing = unadopted / "Justfile"
    existing.write_text("existing:\n    echo existing task\n")
    refused = subprocess.run(  # noqa: S603 -- installation alone must not adopt a repository
        [shell, str(launcher), "current"],
        cwd=unadopted,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert list(unadopted.iterdir()) == [existing]
    assert existing.read_text() == "existing:\n    echo existing task\n"


def test_installed_runtime_exercises_optional_selection_and_full_default(
    repository, tmp_path, installed_python
):
    root, _ = repository
    declare_provider(root)
    python = installed_python
    output = tmp_path / "installed runtime"
    subprocess.run(  # noqa: S603 -- installed generator produces this consumer's own runtime
        [str(python), "-B", "-I", "-m", "signetum.runtime_generation", str(output)],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    script = """
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from _signetum_runtime.git import git_output
from _signetum_runtime.manifest import load_manifest
from _signetum_runtime.repository_selection import select_repository
root=Path(sys.argv[2]); source=git_output(root,"rev-parse","HEAD")
selected=select_repository(root,load_manifest(root/"signetum.toml"),("source.py",),base=source,source=source)
shard=next(s for s in selected.manifest.validation.shards if s.name=="test:check")
assert shard.command[-1]=="tests/test_a.py"
manifest=load_manifest(root/"signetum.toml")
from dataclasses import replace
full=select_repository(root,replace(manifest,impact=replace(manifest.impact,provider=None)),
                       ("docs/readme.md",),base=source,source=source)
assert full.selection.gates==("member",)
assert next(s for s in full.manifest.validation.shards if s.name=="test:check").command[-1]=="tests"
from _signetum_runtime.test_diagnostic import run_test_diagnostic
feedback=run_test_diagnostic(root,"test:check",())
assert feedback["status"]=="diagnostic"
assert not list((root/".git/signetum/validation").glob("*.json"))
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules
print("installed adoption boundaries verified")
"""
    completed = subprocess.run(  # noqa: S603 -- isolated generated runtime from the installed wheel
        [
            str(python),
            "-B",
            "-I",
            "-S",
            "-c",
            script,
            str(output / RUNTIME_DIRECTORY.parent),
            str(root),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "installed adoption boundaries verified"
    assert not git_output(root, "status", "--porcelain")


def test_installed_engine_previews_adopts_and_routes_skill_without_replacing_application(
    local_repository, tmp_path, installed_python
):
    consumer, _ = local_repository
    architecture = consumer / "docs/ARCHITECTURE.md"
    architecture.parent.mkdir()
    architecture.write_text("# Existing application\n")
    (consumer / "Justfile").write_text("test:\n    existing-application-command\n")
    metadata = consumer / "package.json"
    metadata.write_text('{"name":"existing-app"}\n')
    git_output(consumer, "add", ".")
    git_output(consumer, "commit", "-m", "existing application authorities")
    originals = {p.name: p.read_bytes() for p in (metadata, consumer / "Justfile")}
    request = tmp_path / "adoption request.json"
    request.write_text(
        json.dumps(
            {
                "manifest": (consumer / "signetum.toml").read_text(),
                "policy": (consumer / ".agents/repo-dev/repo.yaml").read_text(),
                "interpreter": [sys.executable, "-I", "-S"],
            }
        )
    )
    plan = tmp_path / "reviewed plan.json"
    # The immutable installed payload has no dependencies. Supply only the host's
    # declared dependency directory; do not process editable .pth files or add source.
    invoke = [
        str(installed_python),
        "-B",
        "-I",
        "-c",
        "import sys; from pathlib import Path; sys.path.append(sys.argv.pop(1)); "
        "import signetum; assert Path(signetum.__file__).is_relative_to(Path(sys.prefix)); "
        "from signetum.adoption import main; raise SystemExit(main())",
        str(Path(yaml.__file__).parent.parent),
    ]
    result = subprocess.run(  # noqa: S603 -- installed engine, disposable consumer and literal request
        [
            *invoke,
            "preview",
            "--repository",
            str(consumer),
            "--request",
            str(request),
            "--output",
            str(plan),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    proposal = json.loads(result.stdout)
    assert proposal["status"] == "proposal"
    assert not (consumer / ".agents/repo-dev/run").exists()
    result = subprocess.run(  # noqa: S603 -- apply the exact preview in the disposable consumer
        [
            *invoke,
            "apply",
            "--repository",
            str(consumer),
            "--plan",
            str(plan),
            "--expected-plan",
            proposal["plan_digest"],
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for name, original in originals.items():
        assert (consumer / name).read_bytes() == original
    launcher = tmp_path / "installed skill launcher"
    with ZipFile(next(Path("dist").glob("signetum-*.whl"))) as wheel:
        launcher.write_bytes(wheel.read("signetum/resources/skills/signetum/scripts/signetum"))
    shell = which("sh")
    assert shell is not None
    result = subprocess.run(  # noqa: S603 -- installed launcher discovers the actual adopted local runtime
        [shell, str(launcher), "current"],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["working_set"]["clauses"] == []
    # The existing application metadata stays untouched; adoption did not create
    # Python application metadata or readiness evidence for this non-Python consumer.
    assert not (consumer / "pyproject.toml").exists()
    assert not list((state_root(consumer) / "validation").glob("*.json"))
