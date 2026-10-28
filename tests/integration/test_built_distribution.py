import json
import subprocess
import sys
from pathlib import Path
from shutil import which
from zipfile import ZipFile

from change_fixtures import approve_change
from test_batch_admission import MANIFEST

from signetum.git import git_output
from signetum.manifest import load_manifest
from signetum.runtime_generation import RUNTIME_DIRECTORY, runtime_files
from signetum.validation.repository import configured_validation


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

    assert "signetum/resources/schemas/signetum-v2.schema.json" in names
    assert "signetum/resources/profiles/python-default-v1.toml" in names
    assert "signetum/resources/schemas/validation-graph-v2.schema.json" in names
    assert "signetum/resources/schemas/validation-evidence-v3.schema.json" in names
    assert "signetum/resources/schemas/contracts/release-metadata.schema.json" in names
    assert "signetum/resources/skills/repo-dev/SKILL.md" in names
    assert "signetum/resources/vectors/validation-evidence-v3.json" in names
    # Absence is the contract here, so each value is bound to the reason it
    # must not appear rather than left as a bare literal nobody can extend.
    unrendered_template_placeholder = "placeholder_name"
    build_machine_home = str(Path.home())

    assert unrendered_template_placeholder not in payload
    assert build_machine_home not in payload


def test_installed_wheel_generates_the_same_portable_runtime(tmp_path):
    wheels = tuple(Path("dist").glob("signetum-*.whl"))
    assert len(wheels) == 1
    uv = which("uv")
    assert uv is not None
    environment = tmp_path / "environment"
    python = environment / "bin/python"
    output = tmp_path / "template"
    probe = (
        "from pathlib import Path; import sys,signetum; from importlib.util import find_spec; "
        "assert Path(signetum.__file__).is_relative_to(Path(sys.prefix)); "
        "assert find_spec('pydantic') is None"
    )
    commands = (
        (uv, "venv", "--python", sys.executable, str(environment)),
        (uv, "pip", "install", "--python", str(python), "--no-deps", str(wheels[0].resolve())),
        (str(python), "-I", "-c", probe),
        (str(python), "-I", "-m", "signetum.runtime_generation", str(output)),
    )
    for command in commands:
        subprocess.run(command, check=True, cwd=tmp_path, capture_output=True, text=True)  # noqa: S603 -- fixed tools and disposable artifact paths
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
        [str(python), "-I", "-S", "-c", catalog_probe, str(runtime.parent), str(manifest_path)],
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
from _signetum_runtime.deviations import main
root=Path(sys.argv[2])
output,errors=io.StringIO(),io.StringIO()
status=query(root,TraceabilityManifest(schema_version=1),EvidenceSnapshot(),output,errors)
assert status==0,errors.getvalue()
assert json.loads(output.getvalue())['valid'] is True
commands=[
 ['record','--change','example','--id','installed','--member','plan/installed',
  '--class','implementation_clarification','--summary','Installed authority',
  '--commitment','Keep behavior','--action','Reuse owner','--impact','None'],
 ['resolve','--change','example','--id','installed','--member','plan/installed',
  '--resolution','no_authority_change','--reason','Authority retained'],
 ['status','--change','example'],
]
for command in commands:
 stream=io.StringIO()
 with redirect_stdout(stream):
  status=main(['--repository',str(root),*command])
 assert status==0,stream.getvalue()
assert json.loads(stream.getvalue())['deviation_count']==1
from _signetum_runtime.configuration import configured_validation
from _signetum_runtime.profile_catalog import load_catalog
from _signetum_runtime.manifest import load_manifest
from _signetum_runtime.git import git_output
from _signetum_runtime.lifecycle_validation import validate_workspace
from _signetum_runtime.execution import ShardExecution
from _signetum_runtime.process import run_command
from _signetum_runtime.workspaces import WorkspaceRecord,state_root,write_record
write_record(state_root(root),WorkspaceRecord(1,'plan/installed',sys.argv[3],'member'))
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
