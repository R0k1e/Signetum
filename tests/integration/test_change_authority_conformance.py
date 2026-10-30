"""Independent template queries use the engine's complete change authority."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum.git import git_output
from signetum.traceability.boundary import GitInventoryProvider

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("portable", [False, True])
def test_inventory_cannot_be_redirected_to_a_foreign_repository(tmp_path, monkeypatch, portable):
    root, foreign = tmp_path / "own", tmp_path / "foreign"
    for path, name in ((root, "own.txt"), (foreign, "foreign.txt")):
        path.mkdir()
        git_output(path, "init", "-b", "main")
        (path / name).write_text("tracked")
        git_output(path, "add", name)
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))
    if portable:
        script = (
            "import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
            "from _signetum_runtime.traceability_boundary import GitInventoryProvider; "
            "print(json.dumps(sorted(GitInventoryProvider().read(Path(sys.argv[2])).paths))); "
            "assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules"
        )
        result = subprocess.run(  # noqa: S603 -- isolated generated boundary in disposable repositories
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                script,
                str(ROOT / "tests/fixtures/portable-python/.agents/signetum/runtime"),
                str(root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        observed = json.loads(result.stdout)
    else:
        observed = sorted(GitInventoryProvider().read(root).paths)
    assert observed == ["own.txt"]


@pytest.fixture(name="repository")
def local_only_repository(local_repository):
    return local_repository
