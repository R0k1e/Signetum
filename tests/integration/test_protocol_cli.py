"""The same local utility router runs as an engine and an isolated template."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from change_fixtures import consolidated_approval

from signetum.change_record import parse_change_record
from signetum.git import git_output
from signetum.test_diagnostic import main as diagnostic_main
from signetum.workspaces import WorkspaceRecord, state_root, write_record

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_protocol_authors_and_reviews_one_unapproved_record(repository, frontend):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    git_output(root, "switch", "-c", "plan/protocol")
    write_record(state_root(root), WorkspaceRecord(1, "plan/protocol", base, "member"))
    prefix = (
        [sys.executable, "-m", "signetum.cli", "protocol"]
        if frontend == "engine"
        else [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "template/.agents/repo-dev/runtime/protocol.py"),
        ]
    )
    opened = subprocess.run(  # noqa: S603 -- owned public utilities in a disposable repository
        [*prefix, "change-open", "protocol-example", "--repository", str(root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert opened.returncode == 0, opened.stderr + opened.stdout
    path = root / json.loads(opened.stdout)["files"][0]
    original = path.read_bytes()
    viewed = subprocess.run(  # noqa: S603 -- read-only view of the authored fixture record
        [*prefix, "view", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert viewed.returncode == 0, viewed.stderr
    view = json.loads(viewed.stdout)
    assert view["status"] == "proposal" and view["approval"] is None
    assert view["requirements"][0]["id"] == "REQ-001"
    assert view["contract_digest"].startswith("sha256:")
    assert parse_change_record(path.read_text()).approval is None
    assert path.read_bytes() == original
    legacy_prefix = (
        [sys.executable, "-m", "signetum.deviations"]
        if frontend == "engine"
        else [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "template/.agents/repo-dev/runtime/deviations.py"),
        ]
    )
    refused = subprocess.run(  # noqa: S603 -- the legacy API must not create a second mutation channel
        [
            *legacy_prefix,
            "--repository",
            str(root),
            "record",
            "--change",
            "protocol-example",
            "--id",
            "wrong-channel",
            "--member",
            "plan/protocol",
            "--class",
            "implementation_clarification",
            "--summary",
            "An ordinary implementation finding.",
            "--commitment",
            "Preserve behavior.",
            "--action",
            "Use the current journal.",
            "--impact",
            "No scope change.",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode == 2
    assert not (state_root(root) / "changes/protocol-example/deviations.jsonl").exists()


@pytest.fixture(name="repository")
def local_only_repository(local_repository):
    return local_repository


@pytest.mark.parametrize("frontend", ["engine", "template"])
@pytest.mark.parametrize("fails", [False, True])
def test_explicit_test_diagnostic_uses_one_bounded_owner_without_readiness(
    local_repository, frontend, fails
):
    root, state = local_repository
    observed = state / "test-command.json"
    command = [
        sys.executable,
        "-c",
        "import json,os,sys; from pathlib import Path; "
        f"Path({str(observed)!r}).write_text(json.dumps("
        'dict(workers=os.environ["SIGNETUM_VALIDATION_WORKERS"],arguments=sys.argv[1:]))); '
        f"raise SystemExit({int(fails)})",
    ]
    manifest = root / "signetum.toml"
    manifest.write_text(
        manifest.read_text().replace(
            'name = "test:check"\ncommand = ["true"]',
            'name = "test:check"\nrequires = ["test:prepare"]\n'
            "workers = 8\nworker_memory_mb = 1\ncommand = " + json.dumps(command),
        )
    )
    (root / "uncommitted-user-work").write_text("preserved")
    before = git_output(root, "status", "--porcelain")
    prefix = (
        [sys.executable, "-m", "signetum.cli", "protocol"]
        if frontend == "engine"
        else [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "template/.agents/repo-dev/runtime/protocol.py"),
        ]
    )

    result = subprocess.run(  # noqa: S603 -- public diagnostic in an isolated repository, literal arguments
        [
            *prefix,
            "test",
            "--repository",
            str(root),
            "--shard",
            "test:check",
            "--",
            "--literal",
            "literal argument",
        ],
        env=dict(
            os.environ, SIGNETUM_VALIDATION_WORKERS="4", PYTEST_XDIST_WORKER="enclosing-worker"
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (3 if fails else 0), result.stdout + result.stderr
    assert len(result.stdout.splitlines()) == 1
    outcome = json.loads(result.stdout)
    assert outcome["status"] == ("failed" if fails else "passed")
    assert json.loads(observed.read_text()) == {
        "workers": "1",
        "arguments": ["--literal", "literal argument"],
    }
    assert git_output(root, "status", "--porcelain") == before
    assert not list((state_root(root) / "validation").glob("*.json"))
    if fails:
        assert Path(outcome["log"]).is_file()
    else:
        allocation = outcome["details"]["resource_allocation"]
        assert allocation["workers"] == allocation["enclosing_worker_limit"] == 1

    exact = subprocess.run(  # noqa: S603 -- exact-source gate refuses dirty input before checks
        [*prefix, "test", "--repository", str(root), "--gate", "member", "--exact-source"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert exact.returncode == 3, exact.stdout + exact.stderr
    assert "not clean" in json.loads(exact.stdout)["cause"]

    assert not (state / "attempts").exists(), "single-shard diagnostics do not prepare"
    gated = subprocess.run(  # noqa: S603 -- same public diagnostic, declared dependency graph
        [*prefix, "test", "--repository", str(root), "--gate", "member"],
        env=dict(
            os.environ, SIGNETUM_VALIDATION_WORKERS="4", PYTEST_XDIST_WORKER="enclosing-worker"
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert gated.returncode == (3 if fails else 0), gated.stdout + gated.stderr
    assert json.loads(gated.stdout)["status"] == ("failed" if fails else "passed")
    assert json.loads(observed.read_text()) == {"workers": "1", "arguments": []}
    assert (state / "attempts").read_text() == "1"
    assert git_output(root, "status", "--porcelain") == before
    assert not list((state_root(root) / "validation").glob("*.json"))


@pytest.mark.parametrize("damage", ["unknown-shard", "ratchet"])
def test_diagnostic_refuses_unsupported_execution_before_launch(local_repository, damage):
    root, state = local_repository
    shard = "missing:shard" if damage == "unknown-shard" else "test:check"
    if damage == "ratchet":
        manifest = root / "signetum.toml"
        manifest.write_text(
            manifest.read_text().replace(
                'name = "test:check"\n', 'name = "test:check"\nratchet_command = ["false"]\n'
            )
        )
    assert diagnostic_main(["--repository", str(root), "--shard", shard]) == 2
    for options in (
        ["--gate", "missing"],
        ["--gate", "member", "--", "--literal"],
        ["--gate", "member", "--shard", "test:check"],
    ):
        assert diagnostic_main(["--repository", str(root), *options]) == 2
    if damage == "ratchet":
        assert diagnostic_main(["--repository", str(root), "--gate", "member"]) == 0
    assert not list((state_root(root) / "validation").glob("*.json"))
    assert not (state / "attempts").exists()


def test_adoption_inspection_never_mutates_an_unadopted_repository(local_repository):
    root, _ = local_repository
    before = git_output(root, "status", "--porcelain")
    result = subprocess.run(  # noqa: S603 -- read-only public entrypoint
        [sys.executable, "-m", "signetum.cli", "adopt", "inspect", "--repository", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["operation"] == "adopt-inspect"
    assert git_output(root, "status", "--porcelain") == before


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_semantic_journal_binds_current_change_and_retains_retry_identity(
    local_repository, frontend
):
    root, _ = local_repository
    base = git_output(root, "rev-parse", "HEAD")
    git_output(root, "switch", "-c", "plan/semantic")
    write_record(state_root(root), WorkspaceRecord(1, "plan/semantic", base, "member"))
    consolidated_approval(root, base)
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "approve semantic record")
    prefix = (
        [sys.executable, "-m", "signetum.cli", "protocol"]
        if frontend == "engine"
        else [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "template/.agents/repo-dev/runtime/protocol.py"),
        ]
    )
    arguments = [
        "record",
        "--repository",
        str(root),
        "--id",
        "found",
        "--requirement",
        "REQ-1",
        "--summary",
        "The public entrypoint needs a repair.",
        "--reason",
        "Observed through the real command.",
    ]
    for _ in range(2):
        result = subprocess.run([*prefix, *arguments], capture_output=True, text=True, check=False)  # noqa: S603 -- public CLI in private repository
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["applied_transaction"] == "example/found"
    journal = root / "changes/example/events.jsonl"
    assert len(journal.read_text().splitlines()) == 1
    before = journal.read_bytes()
    result = subprocess.run(  # noqa: S603 -- an invalid foreign requirement cannot mutate history
        [*prefix, *[a if a != "REQ-1" else "FOREIGN" for a in arguments]],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert journal.read_bytes() == before

    for command in (
        [
            "resolve",
            "--id",
            "repair",
            "--target",
            "example/found/observation",
            "--reason",
            "Existing tracked evidence supplies the outcome.",
            "--evidence",
            "seed.txt",
        ],
        [
            "retract",
            "--id",
            "reopen",
            "--target",
            "example/found/observation",
            "--resolution",
            "example/repair/resolution",
            "--reason",
            "Inspect the cause once more.",
        ],
    ):
        result = subprocess.run(  # noqa: S603 -- semantic writes use the same guarded owner
            [*prefix, *command, "--repository", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    assert len(journal.read_text().splitlines()) == 3
