"""The same local utility router runs as an engine and an isolated template."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from signetum.change_record import parse_change_record
from signetum.git import git_output
from signetum.workspaces import WorkspaceRecord, state_root, write_record

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("frontend", ["engine", "template"])
def test_protocol_authors_and_reviews_one_unapproved_record(repository, frontend):
    root, _ = repository
    base = git_output(root, "rev-parse", "HEAD")
    git_output(root, "switch", "-c", "plan/protocol")
    write_record(state_root(root), WorkspaceRecord(1, "plan/protocol", base, "member"))
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
    help_result = subprocess.run(  # noqa: S603 -- helper help must reach the real journal parser
        [*prefix, "record", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--expected-history" in help_result.stdout

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
