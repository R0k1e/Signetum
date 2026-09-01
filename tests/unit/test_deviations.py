from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from shutil import which

import pytest

from reposeal.deviations import (
    DeviationClass,
    DeviationError,
    Discovered,
    ResolutionKind,
    Resolved,
    append_event,
    approval_view,
    ledger_path,
    main,
    read_states,
    reconciliation_summary,
)


def _git(repository: Path, *arguments: str) -> str:
    executable = which("git")
    if executable is None:
        raise RuntimeError("Git executable is unavailable")
    return subprocess.run(  # nosec B603  # noqa: S603
        (executable, "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("test\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial")
    return root


def _discovered(identifier: str = "DEV-001") -> Discovered:
    return Discovered(
        id=identifier,
        change_id="example",
        member="impl/example",
        at=datetime.now(UTC),
        summary="An accepted decision conflicts with the approved behavior.",
        classification=DeviationClass.DECISION_REQUIRED,
        original_commitment="Preserve the existing behavior.",
        action="Freeze the affected implementation.",
        impact="Independent work can continue.",
    )


def test_linked_worktree_resolves_the_same_ledger(repository: Path, tmp_path: Path) -> None:
    member = tmp_path / "member"
    _git(repository, "worktree", "add", "-b", "impl/example", str(member))

    assert ledger_path(repository, "example") == ledger_path(member, "example")


def test_append_only_events_reduce_to_one_terminal_state(repository: Path) -> None:
    append_event(repository, _discovered())
    target = repository / "docs" / "decisions" / "ADP-example.md"
    target.parent.mkdir(parents=True)
    target.write_text("# ADP\n\nStatus: Accepted\n\nSupersedes: ADR-0001\n", encoding="utf-8")
    append_event(
        repository,
        Resolved(
            id="DEV-001",
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=ResolutionKind.RESOLVED_IN_DECISION,
            targets=("docs/decisions/ADP-example.md",),
            reason="The accepted decision now states the authoritative behavior.",
            implemented=True,
        ),
    )

    states = read_states(repository, "example")
    assert len(states) == 1
    assert states[0].resolution is not None
    assert reconciliation_summary(repository, ("example",))["deviation_count"] == 1


def test_pending_deviation_refuses_reconciliation(repository: Path) -> None:
    append_event(repository, _discovered())

    with pytest.raises(DeviationError, match="unresolved deviations: example/DEV-001"):
        reconciliation_summary(repository, ("example",))


def test_decision_required_implementation_needs_behavior_authority(repository: Path) -> None:
    append_event(repository, _discovered())
    append_event(
        repository,
        Resolved(
            id="DEV-001",
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=ResolutionKind.NO_AUTHORITY_CHANGE,
            reason="No document changed.",
            implemented=True,
        ),
    )

    with pytest.raises(DeviationError, match="implemented without authority"):
        reconciliation_summary(repository, ("example",))


def test_malformed_event_is_not_ignored(repository: Path) -> None:
    path = ledger_path(repository, "example")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"event": "discovered"}) + "\n", encoding="utf-8")

    with pytest.raises(DeviationError, match="invalid deviation event at line 1"):
        read_states(repository, "example")


def test_approval_view_projects_approved_change(repository: Path) -> None:
    change = repository / "changes" / "example"
    (change / "specs").mkdir(parents=True)
    (change / "review.toml").write_text(
        """[review]
[[review.clauses]]
id = "REQ-001"
statement = "The user receives one review."
""",
        encoding="utf-8",
    )
    (change / "specs" / "example.toml").write_text(
        """[specification]
status = "approved"
implementation_authorized = true
acceptance = ["The review names the delivered behavior."]
""",
        encoding="utf-8",
    )

    projected = approval_view(repository, "example")

    assert projected["outcomes"] == ["The user receives one review."]
    assert projected["acceptance"] == ["The review names the delivered behavior."]


def test_support_cli_records_resolves_and_reports(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    common = (
        "--repository",
        str(repository),
    )
    recorded = main(
        [
            *common,
            "record",
            "--change",
            "example",
            "--id",
            "DEV-001",
            "--member",
            "impl/example",
            "--class",
            "implementation_clarification",
            "--summary",
            "The implementation authority is elsewhere.",
            "--commitment",
            "Preserve observable behavior.",
            "--action",
            "Use the existing authority.",
            "--impact",
            "No behavior changes.",
        ]
    )
    assert recorded == 0
    assert json.loads(capsys.readouterr().out)["status"] == "recorded"

    resolved = main(
        [
            *common,
            "resolve",
            "--change",
            "example",
            "--id",
            "DEV-001",
            "--member",
            "impl/example",
            "--resolution",
            "no_authority_change",
            "--reason",
            "The public behavior and authority are unchanged.",
        ]
    )
    assert resolved == 0
    assert json.loads(capsys.readouterr().out)["status"] == "resolved"

    status = main([*common, "status", "--change", "example"])
    assert status == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "reconciled"
    assert report["deviation_count"] == 1


def test_support_cli_refuses_unknown_resolution(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main(
        [
            "--repository",
            str(repository),
            "resolve",
            "--change",
            "example",
            "--id",
            "DEV-404",
            "--member",
            "impl/example",
            "--resolution",
            "rejected",
            "--reason",
            "The discovery is unrelated.",
        ]
    )

    assert result == 2
    assert "deviation is absent" in json.loads(capsys.readouterr().out)["reason"]
