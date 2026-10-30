"""Standalone policy reading preserves full safe YAML and declared branch identity."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum.git import git_output
from signetum.policy import delivery_policy

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "document,branch",
    [
        ("delivery:\n  branch: release\n", "release"),
        ('delivery: {branch: "release#stable"}\n', "release#stable"),
        ("common: &base {branch: release}\ndelivery: {<<: *base}\n", "release"),
        ("delivery:\n  branch: >-\n    release\n", "release"),
        ('{"delivery": {"branch": "release/v1"}}', "release/v1"),
        ("delivery: {branch: true}", None),
        ("delivery: {branch: release, unknown: true}", None),
        ("delivery: {branch: bad..branch}", None),
        ('delivery: {branch: ""}', None),
        ("[]", None),
        ("repository: {}", None),
        ('delivery: !!python/object/apply:builtins.eval ["1+1"]', None),
    ],
)
def test_native_policy_has_identical_safe_yaml_semantics(tmp_path, document, branch):
    git_output(tmp_path, "init", "-b", "main")
    path = tmp_path / ".agents/signetum/repo.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(document)
    if branch is None:
        with pytest.raises(ValueError):
            delivery_policy(tmp_path)
        expected = {"invalid": True}
    else:
        assert delivery_policy(tmp_path).branch == branch
        expected = {"branch": branch}
    script = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from _signetum_runtime.policy import delivery_policy
try:
 result={'branch':delivery_policy(Path(sys.argv[2])).branch}
except ValueError:
 result={'invalid':True}
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules and 'yaml' not in sys.modules
print(json.dumps(result))
"""
    result = subprocess.run(  # noqa: S603 -- isolated copied policy, real disposable Git repository
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            script,
            str(ROOT / "template/.agents/signetum/runtime"),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected
