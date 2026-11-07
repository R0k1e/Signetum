"""The repository Justfile hands each recipe argument to the engine intact."""

import json
import os
import shutil
import subprocess  # nosec B404 -- fixed just executable, argv, no shell
import sys
from pathlib import Path

import pytest

JUSTFILE = Path(__file__).parents[2] / "Justfile"


def recorded(tmp_path, *arguments):
    shutil.copyfile(JUSTFILE, tmp_path / "Justfile")
    tools = tmp_path / "bin"
    tools.mkdir()
    calls = tmp_path / "calls.jsonl"
    mise = tools / "mise"
    mise.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"with open({str(calls)!r}, 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
    )
    mise.chmod(0o755)
    just = shutil.which("just")
    assert just is not None
    environment = dict(os.environ, PATH=f"{tools}{os.pathsep}{os.environ['PATH']}")
    subprocess.run(  # noqa: S603  # nosec B603 -- fixed executable, no shell
        [just, *arguments], cwd=tmp_path, env=environment, check=True, capture_output=True
    )
    return [json.loads(line) for line in calls.read_text().splitlines()]


@pytest.mark.parametrize(
    ("arguments", "engine"),
    [
        (
            ("maintenance", "workspace-abandon", "--reason", "a; b c"),
            ["maintenance", "workspace-abandon", "--reason", "a; b c"],
        ),
        (
            ("batch-admit", "batch dir", "--member", "x; touch injected"),
            ["batch-admit", "--batch", "batch dir", "--member", "x; touch injected"],
        ),
    ],
)
def test_recipes_forward_each_argument_intact(tmp_path, arguments, engine):
    calls = recorded(tmp_path, *arguments)
    assert calls == [["exec", "--", "uv", "run", "signetum", *engine]]
    assert not (tmp_path / "injected").exists()
