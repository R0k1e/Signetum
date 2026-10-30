"""Independent template queries use the engine's complete change authority."""

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from change_fixtures import approve_legacy_change as approve_change

from signetum import deviations
from signetum.git import git_output
from signetum.status.models import EvidenceSnapshot
from signetum.traceability.boundary import GitInventoryProvider, TraceabilityManifest
from signetum.traceability.cli import query

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "damage",
    [
        "valid",
        "schema",
        "duplicate",
        "missing-plan",
        "wrong-owner",
        "clause-type",
        "date",
        "decision",
        "custom-roots",
    ],
)
def test_native_traceability_documents_and_verdicts_match(repository, damage):
    root, _ = repository
    approve_change(root)
    review = root / "changes/example/review.toml"
    spec = root / "changes/example/specs/behavior.toml"
    changes, decisions = "changes", "docs/decisions"
    if damage == "schema":
        review.write_text(review.read_text().replace("schema_version = 1", "schema_version = 2"))
    elif damage == "duplicate":
        clause = review.read_text().split("[[review.clauses]]")[1]
        review.write_text(review.read_text() + "\n[[review.clauses]]" + clause)
    elif damage == "missing-plan":
        (root / "changes/example/plans/behavior.md").unlink()
    elif damage == "wrong-owner":
        spec.write_text(
            spec.read_text().replace('id = "example/behavior"', 'id = "other/behavior"')
        )
    elif damage == "clause-type":
        review.write_text(review.read_text().replace('id = "REQ-001"', "id = 12"))
    elif damage == "date":
        review.write_text(
            review.read_text().replace(
                'status = "approved"', 'status = "approved"\nrecorded_at = 2026-10-29'
            )
        )
    elif damage == "decision":
        decision = root / "docs/decisions/ADP-choice.md"
        decision.parent.mkdir(parents=True)
        decision.write_text(
            "# Pending choice\nStatus: Proposed\nSupersedes: None\nSuperseded by: None\n"
        )
        spec.write_text(
            spec.read_text().replace(
                "plan = ", 'decisions = ["docs/decisions/ADP-choice.md"]\nplan = '
            )
        )
    elif damage == "custom-roots":
        for path in (review, spec, root / "changes/example/plans/behavior.md"):
            path.write_text(path.read_text().replace("changes/", "requests/"))
        (root / "changes").rename(root / "requests")
        changes, decisions = "requests", "policy/decisions"
    stdout, stderr = io.StringIO(), io.StringIO()
    status = query(
        root,
        TraceabilityManifest(schema_version=1, changes_root=changes, decision_roots=(decisions,)),
        EvidenceSnapshot(),
        stdout,
        stderr,
    )
    script = ROOT / "template/.agents/repo-dev/runtime/traceability.py"
    result = subprocess.run(  # noqa: S603 -- isolated interpreter and disposable repository
        [
            sys.executable,
            "-I",
            "-S",
            str(script),
            "--repository",
            str(root),
            "--changes-root",
            changes,
            "--decision-root",
            decisions,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == status, result.stdout + result.stderr
    assert json.loads(result.stdout) == json.loads(stdout.getvalue())


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
                str(ROOT / "template/.agents/repo-dev/runtime"),
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


def test_native_ledger_frontends_share_state_and_refuse_wrong_owner_without_writing(
    repository, capsys
):
    root, _ = repository
    approve_change(root)
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "approve ledger change")
    git_output(root, "switch", "-c", "plan/shared-ledger")
    script = ROOT / "template/.agents/repo-dev/runtime/deviations.py"

    def copied(*args):
        return subprocess.run(  # noqa: S603 -- standalone template CLI and isolated fixture
            [sys.executable, "-I", "-S", str(script), "--repository", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    assert (
        deviations.main(
            [
                "--repository",
                str(root),
                "record",
                "--change",
                "example",
                "--id",
                "interop",
                "--member",
                "plan/shared-ledger",
                "--class",
                "implementation_clarification",
                "--summary",
                "Use one ledger",
                "--commitment",
                "Keep behavior",
                "--action",
                "Reuse owner",
                "--impact",
                "No behavior change",
            ]
        )
        == 0
    )
    capsys.readouterr()
    ledger = deviations.ledger_path(root, "example")
    original = ledger.read_bytes()
    wrong = copied(
        "resolve",
        "--change",
        "example",
        "--id",
        "interop",
        "--member",
        "other",
        "--resolution",
        "no_authority_change",
        "--reason",
        "No authority change",
    )
    assert wrong.returncode == 2
    assert ledger.read_bytes() == original
    pending = copied("status", "--change", "example")
    assert pending.returncode == 2
    assert "unresolved deviations" in json.loads(pending.stdout)["reason"]
    resolved = copied(
        "resolve",
        "--change",
        "example",
        "--id",
        "interop",
        "--member",
        "plan/shared-ledger",
        "--resolution",
        "no_authority_change",
        "--reason",
        "The approved authority still applies",
    )
    assert resolved.returncode == 0, resolved.stdout + resolved.stderr
    assert deviations.read_states(root, "example")[0].resolution is not None
    assert deviations.main(["--repository", str(root), "status", "--change", "example"]) == 0
    source = json.loads(capsys.readouterr().out)
    target = copied("status", "--change", "example")
    assert target.returncode == 0, target.stdout + target.stderr
    assert json.loads(target.stdout) == source


@pytest.fixture(name="repository")
def local_only_repository(local_repository):
    return local_repository
