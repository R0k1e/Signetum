"""Both distributions execute the same durable workspace record contract."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("module", "source"),
    [("signetum.workspaces", ROOT / "skills/signetum/scripts/engine")],
)
def test_workspace_storage_is_portable_and_immutable(tmp_path, module, source):
    script = """import importlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
m=importlib.import_module(sys.argv[2])
root=Path(sys.argv[3])
base='a'*40
record=m.WorkspaceRecord(schema_version=1,branch='plan/example',base=base,kind='member')
path=m.write_record(root,record)
original=path.read_bytes()
for values in ({'base':'b'*40},{'kind':'batch'},{'members':('/other',)}):
    values={'schema_version':1,'branch':'plan/example','base':base,'kind':'member',**values}
    try: m.write_record(root,m.WorkspaceRecord(**values))
    except m.WorkspaceError: pass
    else: raise AssertionError('record identity was replaced')
    assert path.read_bytes()==original
assert m.read_record(root,'plan/example')==record
m.claim_change(root,'example','plan/example')
m.claim_change(root,'example','plan/example')
try: m.claim_change(root,'example','plan/another')
except m.WorkspaceError: pass
else: raise AssertionError('change acquired a second owner')
invalid=({'schema_version':True},{'base':'a'*42},
    {'members':['/same','/same']},{'branch':'other'})
for bad in invalid:
    data={'schema_version':1,'branch':'plan/example','base':base,'kind':'member',**bad}
    path.write_text(json.dumps(data))
    try: m.read_record(root,'plan/example')
    except m.WorkspaceError: pass
    else: raise AssertionError('invalid record was accepted')
authorization=m.BatchAuthorization(
    'Owner','Fixture approval','2026-11-09T00:00:00+00:00',('plan/example',))
record=m.WorkspaceRecord(2,'batch/example',base,'batch',('plan/example',),authorization=authorization)
path=m.write_record(root,record)
assert m.parse_record(json.loads(path.read_text()))==record
m.advance_batch_base(root,record.branch,base,'b'*40)
assert m.read_record(root,record.branch).authorization==authorization
for schema,kind in ((1,'batch'),(2,'member')):
    try: m.WorkspaceRecord(schema,'other',base,kind,('plan/example',),authorization=authorization)
    except m.WorkspaceError: pass
    else: raise AssertionError('authorization accepted outside schema-2 batch')
assert 'pydantic' not in sys.modules
"""
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and disposable storage contract
        [sys.executable, "-I", "-S", "-c", script, str(source), module, str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
