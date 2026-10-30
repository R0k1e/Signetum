"""A language binding proposal is literal, portable and has no execution effects."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum.manifest import manifest_from_mapping

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("frontend", ["engine", "template"])
@pytest.mark.parametrize("language", ["python", "node", "rust"])
def test_runner_proposal_preserves_existing_argv_without_running_or_adopting_it(
    tmp_path, frontend, language
):
    sentinel = tmp_path / "must-not-execute"
    request = tmp_path / "runner request"
    command = [sys.executable, "-c", f"from pathlib import Path; Path({str(sentinel)!r}).touch()"]
    data = {
        "language": language,
        "command": command,
        "tools": [{"name": "existing", "identity_command": ["existing", "--version"]}],
    }
    request.write_text(json.dumps(data))
    prefix = (
        [sys.executable, "-m", "signetum.protocol_cli"]
        if frontend == "engine"
        else [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "template/.agents/repo-dev/runtime/protocol.py"),
        ]
    )
    result = subprocess.run(  # noqa: S603 -- the proposed command itself must remain unexecuted
        [*prefix, "runner", "--request", str(request)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    proposal = json.loads(result.stdout)
    assert proposal["status"] == "proposal"
    fragment = proposal["fragment"]
    assert fragment["profiles"]["enabled"] == [f"{language}-existing@1"]
    assert fragment["validation"]["shards"][0]["command"] == command
    retired_retry_tuning = {"recovery_window", "recovery_threshold"}
    assert retired_retry_tuning.isdisjoint(fragment["validation"])
    manifest = manifest_from_mapping(
        {
            "schema_version": 2,
            "signetum": {"protocol": 2, "template_version": "0.2.0"},
            "repository": {
                "architecture": "docs/ARCHITECTURE.md",
                "specifications": "changes/*/specs/*.toml",
                "plans": "changes/*/plans/*.md",
                "decisions": "docs/decisions",
            },
            **fragment,
        }
    )
    assert manifest.validation.shards[0].command == tuple(command)
    assert not sentinel.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["runner request"]
