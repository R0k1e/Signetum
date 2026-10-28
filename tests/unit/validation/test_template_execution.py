"""Native template execution honors dependencies and independent failures."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum.git import git_output


@pytest.mark.parametrize("fail_bootstrap", [False, True])
def test_template_executes_dependency_closure_and_skips_blocked_checks(
    repository, tmp_path, fail_bootstrap
):
    root, _ = repository
    observed = tmp_path / "observed"

    def command(name, fail=False):
        script = (
            "from pathlib import Path; import sys; p=Path(sys.argv[1]); "
            "p.write_text((p.read_text() if p.exists() else '') + sys.argv[2] + '\\n'); "
            "sys.exit(int(sys.argv[3]))"
        )
        return json.dumps([sys.executable, "-c", script, str(observed), name, str(int(fail))])

    manifest = root / "signetum.toml"
    manifest.write_text(
        manifest.read_text()
        .split("[validation]")[0]
        .replace(
            "[repository]",
            'evidence_protocol = "reposeal.validation-evidence@3"\n'
            + 'evidence_schema_digest = "sha256:'
            + "0" * 64
            + '"\n[repository]',
        )
        + f"""[validation]
[[validation.shards]]
name = "core:bootstrap"
command = {command("bootstrap", fail_bootstrap)}
[[validation.shards]]
name = "core:dependent"
command = {command("dependent")}
requires = ["core:bootstrap"]
[[validation.shards]]
name = "core:independent"
command = {command("independent")}
[[validation.gates]]
name = "member"
shards = ["core:dependent", "core:independent"]
"""
    )
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare execution fixture")
    runtime = Path(__file__).parents[3] / "template/.agents/repo-dev/runtime"
    script = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import lifecycle
try:
    lifecycle._run_gate(Path(sys.argv[2]),'member')
except lifecycle.AdmissionError as error:
    result={'status':'failed','reason':str(error)}
else:
    result={'status':'passed'}
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules
print(json.dumps(result))
"""
    completed = subprocess.run(  # noqa: S603 -- fixed isolated Python and native fixture commands
        [sys.executable, "-I", "-S", "-c", script, str(runtime), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    if fail_bootstrap:
        assert result["status"] == "failed"
        assert "core:dependent: skipped after core:bootstrap" in result["reason"]
        assert observed.read_text().splitlines() == ["bootstrap", "independent"]
    else:
        assert result["status"] == "passed"
        assert observed.read_text().splitlines() == ["bootstrap", "dependent", "independent"]
