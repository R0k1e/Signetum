"""Installed-independent command supervision survives caller termination."""

import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]


@pytest.mark.parametrize(
    "runtime,module",
    [
        (ROOT / "src", "signetum.validation.process"),
        (ROOT / "template/.agents/repo-dev/runtime", "_signetum_runtime.process"),
    ],
)
@pytest.mark.parametrize("nested", [False, True])
def test_caller_death_terminates_owned_commands_without_site_packages(
    tmp_path, runtime, module, nested
):
    started = tmp_path / "started"
    orphan = tmp_path / "orphan"
    header = (
        "import importlib,sys; from pathlib import Path; "
        f"sys.path.insert(0,{str(runtime)!r}); "
        f"run_command=importlib.import_module({module!r}).run_command; "
        "assert 'pydantic' not in sys.modules; "
    )
    child = (
        "import sys,time; from pathlib import Path; "
        "Path(sys.argv[1]).touch(); time.sleep(1); Path(sys.argv[2]).touch()"
    )
    invocation = [sys.executable, "-I", "-S", "-c", child, str(started), str(orphan)]
    if nested:
        inner = header + f"run_command(Path.cwd(),{invocation!r},timeout_seconds=30)"
        invocation = [sys.executable, "-I", "-S", "-c", inner]
    script = header + f"run_command(Path.cwd(),{invocation!r},timeout_seconds=30)"
    with subprocess.Popen(  # noqa: S603 -- isolated interpreter and fixture-only argv
        [sys.executable, "-I", "-S", "-c", script],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as caller:
        try:
            deadline = time.monotonic() + 5
            while not started.exists() and caller.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert started.exists(), "owned command never started"
            caller.kill()
            caller.communicate(timeout=3)
        finally:
            if caller.poll() is None:
                caller.kill()
                caller.communicate(timeout=3)
    time.sleep(1.2)
    assert not orphan.exists(), "caller termination left an owned descendant running"
