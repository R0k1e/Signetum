import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from shutil import which
from urllib.parse import quote

import pytest

from signetum.impact import select_impact
from signetum.manifest import ImpactRule, load_manifest
from signetum.repository_selection import select_repository


def test_multiple_language_rules_compose_as_one_deterministic_selection() -> None:
    rules = (
        ImpactRule(
            name="python.source",
            paths=("backend/**",),
            profiles=("python-default@1",),
            gates=("python.type", "python.unit"),
            shards=("python.unit",),
        ),
        ImpactRule(
            name="typescript.source",
            paths=("frontend/**",),
            profiles=("typescript-default@1",),
            gates=("typescript.type", "typescript.unit"),
            shards=("typescript.unit",),
            requires_final=True,
        ),
    )

    selection = select_impact(("backend/api.py", "frontend/view.ts", "README.md"), rules)

    assert selection.rules == ("python.source", "typescript.source")
    assert selection.profiles == ("python-default@1", "typescript-default@1")
    assert selection.gates == (
        "python.type",
        "python.unit",
        "typescript.type",
        "typescript.unit",
    )
    assert selection.unexplained == ("README.md",)
    assert selection.requires_final is True


def test_empty_diff_does_not_invent_validation() -> None:
    assert select_impact((), ()).requires_final is False


@pytest.mark.parametrize(
    "files",
    [
        (),
        ("backend/a.py",),
        ("frontend/tests/view.ts",),
        ("backend/a.py", "frontend/test_view.ts", "README.md"),
        ("backend",),
    ],
)
def test_independent_template_defaults_to_the_same_full_checks_as_the_engine(tmp_path, files):
    executable = which("git")
    assert executable is not None

    def git(*args):
        result = subprocess.run(  # noqa: S603 -- fixed Git and fixture arguments
            [executable, "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    git("init", "-b", "plan/example")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    (tmp_path / "signetum.toml").write_text("""schema_version = 2
[signetum]
protocol = 2
template_version = "0.2.0"
[repository]
architecture = "architecture.md"
specifications = "changes/*/specs/*.toml"
plans = "changes/*/plans/*.md"
decisions = "decisions"
[[impact.rules]]
name = "python.source"
paths = ["backend/**"]
profiles = ["python-default@1"]
shards = ["test:unit"]
[[impact.rules]]
name = "frontend.source"
paths = ["frontend/**"]
profiles = ["typescript-default@1"]
shards = ["test:unit", "test:web"]
requires_final = true
[[validation.shards]]
name = "test:unit"
command = ["true"]
[[validation.shards]]
name = "test:web"
command = ["true"]
[[validation.gates]]
name = "member"
shards = ["test:unit", "test:web"]
[[validation.gates]]
name = "final"
shards = ["test:unit", "test:web"]
""")
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    record = tmp_path / f".git/signetum/workspaces/{quote('plan/example', safe='')}.json"
    record.parent.mkdir(parents=True)
    record.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "branch": "plan/example",
                "base": base,
                "kind": "member",
                "members": [],
            }
        )
    )
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")
    git("add", ".")
    git("commit", "--allow-empty", "-m", "implementation")
    runtime = Path(__file__).parents[2] / "template/.agents/repo-dev/runtime"
    script = (
        "import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
        "from _signetum_runtime import lifecycle; "
        "selected=lifecycle.changed(Path(sys.argv[2]),True,validate_only=True); "
        "print(json.dumps(selected['selection'])); "
        "assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules"
    )
    completed = subprocess.run(  # noqa: S603 -- fixed isolated interpreter and fixture argv
        [sys.executable, "-I", "-S", "-c", script, str(runtime), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if not files:
        assert completed.returncode != 0
        assert "no committed contribution" in completed.stderr
        return
    assert completed.returncode == 0, completed.stderr
    selected = select_repository(
        tmp_path,
        load_manifest(tmp_path / "signetum.toml"),
        tuple(sorted(files)),
        base=base,
        source=git("rev-parse", "HEAD"),
    ).selection
    assert selected.shards == ("test:unit", "test:web")
    assert selected.gates == ("member",)
    assert selected.rules == ()
    assert selected.requires_final is True
    expected = json.loads(json.dumps(asdict(selected)))
    assert json.loads(completed.stdout) == expected
