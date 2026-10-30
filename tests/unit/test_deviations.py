from __future__ import annotations

import fcntl
import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from shutil import which

import pytest
from change_fixtures import approve_change
from test_batch_admission import MANIFEST

from signetum.deviations import (
    DeviationClass,
    DeviationError,
    DeviationState,
    Discovered,
    ResolutionKind,
    Resolved,
    append_event,
    approval_view,
    event_json,
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
    _git(root, "init", "-b", "impl/example")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("test\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial")
    (root / "changes/example").mkdir(parents=True)
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
    _git(repository, "worktree", "add", "-b", "impl/linked", str(member))

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
disposition = "covered"
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


def test_discovery_must_be_written_by_the_package_branch(repository):
    wrong = replace(_discovered(), **{"member": "impl/elsewhere"})
    with pytest.raises(DeviationError, match="not the branch checked out"):
        append_event(repository, wrong)
    assert read_states(repository, "example") == ()


def test_discovery_requires_the_change_package_in_the_member(repository):
    missing = replace(_discovered(), **{"change_id": "missing"})
    with pytest.raises(DeviationError, match="package changes/missing is absent"):
        append_event(repository, missing)
    assert read_states(repository, "missing") == ()


def test_a_linked_member_cannot_resolve_another_active_members_discovery(repository, tmp_path):
    append_event(repository, _discovered())
    other = tmp_path / "other"
    _git(repository, "worktree", "add", "-b", "impl/other", str(other))
    resolution = Resolved(
        id="DEV-001",
        change_id="example",
        member="impl/example",
        at=datetime.now(UTC),
        resolution=ResolutionKind.NO_AUTHORITY_CHANGE,
        reason="Investigated",
        implemented=False,
    )
    with pytest.raises(DeviationError, match="not the branch checked out"):
        append_event(other, resolution)
    assert read_states(repository, "example")[0].resolution is None


def test_new_discovery_binds_the_observed_commit(repository):
    event = _discovered()
    append_event(repository, event)
    state = read_states(repository, "example")[0]
    assert state.discovered.source_commit == _git(repository, "rev-parse", "HEAD")
    forged = replace(event, **{"id": "forged", "source_commit": "a" * 40})
    with pytest.raises(DeviationError, match="observed member commit"):
        append_event(repository, forged)


def test_unbound_legacy_discovery_is_not_silently_excluded(repository):
    event = json.loads(event_json(_discovered()))
    event.pop("source_commit")
    path = ledger_path(repository, "example")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(event) + "\n")
    with pytest.raises(DeviationError, match="unresolved deviations"):
        reconciliation_summary(repository, ("example",), member_tips={"impl/example": ("HEAD",)})


@pytest.mark.parametrize(
    "kind", [ResolutionKind.DEFERRED, ResolutionKind.RESOLVED_IN_SPECIFICATION]
)
def test_specification_resolution_cannot_point_to_an_arbitrary_file(repository, kind):
    event = _discovered()
    append_event(repository, event)
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=kind,
            targets=("README.md",),
            reason="Test authority.",
            implemented=False,
        ),
    )
    with pytest.raises(DeviationError, match="specification"):
        reconciliation_summary(repository, ("example",))


@pytest.mark.parametrize("status", ["withdrawn", "superseded"])
def test_deferred_target_must_be_an_active_specification(repository, status):
    approve_change(repository, "follow-up")
    target = repository / "changes/follow-up/specs/behavior.toml"
    target.write_text(target.read_text().replace('status = "approved"', f'status = "{status}"'))
    event = _discovered()
    append_event(repository, event)
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=ResolutionKind.DEFERRED,
            targets=(target.relative_to(repository).as_posix(),),
            reason="Follow-up.",
            implemented=False,
        ),
    )
    with pytest.raises(DeviationError, match="active specification"):
        reconciliation_summary(repository, ("example",))


def test_deferred_target_cannot_belong_to_a_completed_review(repository):
    approve_change(repository, "follow-up")
    review = repository / "changes/follow-up/review.toml"
    review.write_text(review.read_text().replace('status = "approved"', 'status = "completed"'))
    event = _discovered()
    append_event(repository, event)
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=ResolutionKind.DEFERRED,
            targets=("changes/follow-up/specs/behavior.toml",),
            reason="Follow-up.",
            implemented=False,
        ),
    )
    with pytest.raises(DeviationError, match="active specification"):
        reconciliation_summary(repository, ("example",))


@pytest.mark.parametrize(
    "kind", [ResolutionKind.DEFERRED, ResolutionKind.RESOLVED_IN_SPECIFICATION]
)
def test_valid_specification_retains_its_resolution_and_evidence(repository, kind):
    approve_change(repository, "follow-up")
    event = _discovered()
    append_event(repository, event)
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=kind,
            targets=("changes/follow-up/specs/behavior.toml",),
            reason="Named authority.",
            implemented=kind != ResolutionKind.DEFERRED,
        ),
    )
    summary = reconciliation_summary(repository, ("example",))
    assert summary["deviation_count"] == 1
    assert summary["unfinished_work"] == (
        ["example/DEV-001"] if kind == ResolutionKind.DEFERRED else []
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "draft_spec",
        "unauthorized",
        "draft_review",
        "draft_plan",
        "wrong_plan",
        "wrong_review",
        "missing_plan",
    ],
)
def test_specification_resolution_requires_approved_linked_authority(repository, mutation):
    approve_change(repository, "follow-up")
    package = repository / "changes/follow-up"
    spec = package / "specs/behavior.toml"
    review = package / "review.toml"
    plan = package / "plans/behavior.md"
    if mutation == "draft_spec":
        spec.write_text(spec.read_text().replace('status = "approved"', 'status = "draft"'))
    elif mutation == "unauthorized":
        spec.write_text(
            spec.read_text().replace(
                "implementation_authorized = true", "implementation_authorized = false"
            )
        )
    elif mutation == "draft_review":
        review.write_text(review.read_text().replace('status = "approved"', 'status = "draft"'))
    elif mutation == "draft_plan":
        plan.write_text(plan.read_text().replace("Status: approved", "Status: draft"))
    elif mutation == "wrong_plan":
        plan.write_text(
            plan.read_text().replace(
                "Specification: changes/follow-up/specs/behavior.toml",
                "Specification: changes/other/specs/behavior.toml",
            )
        )
    elif mutation == "wrong_review":
        spec.write_text(spec.read_text().replace('id = "follow-up"', 'id = "other"'))
    elif mutation == "missing_plan":
        plan.unlink()
    event = _discovered()
    append_event(repository, event)
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=ResolutionKind.RESOLVED_IN_SPECIFICATION,
            targets=("changes/follow-up/specs/behavior.toml",),
            reason="Named authority.",
            implemented=True,
        ),
    )
    with pytest.raises(DeviationError, match="specification"):
        reconciliation_summary(repository, ("example",))


@pytest.mark.parametrize("standing", ["draft", "completed"])
def test_active_draft_followup_and_accepted_history_keep_distinct_roles(repository, standing):
    approve_change(repository, "follow-up")
    package = repository / "changes/follow-up"
    review = package / "review.toml"
    review.write_text(review.read_text().replace('status = "approved"', f'status = "{standing}"'))
    if standing == "draft":
        spec = package / "specs/behavior.toml"
        spec.write_text(
            spec.read_text()
            .replace('status = "approved"', 'status = "draft"')
            .replace("implementation_authorized = true", "implementation_authorized = false")
        )
    event = _discovered()
    append_event(repository, event)
    kind = (
        ResolutionKind.DEFERRED if standing == "draft" else ResolutionKind.RESOLVED_IN_SPECIFICATION
    )
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=kind,
            targets=("changes/follow-up/specs/behavior.toml",),
            reason="Named authority.",
            implemented=standing != "draft",
        ),
    )
    assert reconciliation_summary(repository, ("example",))["deviation_count"] == 1


def test_resolve_cli_refuses_invalid_authority_without_appending_resolution(repository, capsys):
    append_event(repository, _discovered())
    result = main(
        [
            "--repository",
            str(repository),
            "resolve",
            "--change",
            "example",
            "--id",
            "DEV-001",
            "--member",
            "impl/example",
            "--resolution",
            "deferred",
            "--target",
            "README.md",
            "--reason",
            "Invalid authority.",
        ]
    )
    assert result == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
    assert read_states(repository, "example")[0].resolution is None


def test_resolution_cannot_follow_a_symlink_outside_the_repository(repository, tmp_path):
    external = tmp_path / "external.md"
    external.write_text("External authority.")
    (repository / "authority.md").symlink_to(external)
    event = _discovered()
    append_event(repository, event)
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=ResolutionKind.RESOLVED_IN_ARCHITECTURE,
            targets=("authority.md",),
            reason="External authority.",
            implemented=False,
        ),
    )
    with pytest.raises(DeviationError, match="escapes the repository"):
        reconciliation_summary(repository, ("example",))


def test_public_transitions_refuse_duplicates_without_changing_the_ledger(repository, capsys):
    append_event(repository, _discovered())
    path = ledger_path(repository, "example")
    initial = path.read_bytes()
    record = [
        "--repository",
        str(repository),
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
        "Duplicate.",
        "--commitment",
        "Retain evidence.",
        "--action",
        "Record.",
        "--impact",
        "No change.",
    ]
    assert main(record) == 2
    assert path.read_bytes() == initial
    resolve = [
        "--repository",
        str(repository),
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
        "Existing authority.",
    ]
    assert main(resolve) == 0
    resolved = path.read_bytes()
    assert main(resolve) == 2
    assert path.read_bytes() == resolved
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == "refused"


def test_invalid_resolution_can_be_corrected_through_the_public_api(repository, capsys):
    append_event(repository, _discovered())
    command = [
        "--repository",
        str(repository),
        "resolve",
        "--change",
        "example",
        "--id",
        "DEV-001",
        "--member",
        "impl/example",
        "--resolution",
        "deferred",
        "--reason",
        "Explicit follow-up.",
        "--target",
    ]
    assert main([*command, "README.md"]) == 2
    assert read_states(repository, "example")[0].resolution is None
    approve_change(repository, "follow-up")
    assert main([*command, "changes/follow-up/specs/behavior.toml"]) == 0
    assert reconciliation_summary(repository, ("example",))["unfinished_work"] == [
        "example/DEV-001"
    ]
    capsys.readouterr()


def test_an_active_public_update_refuses_another_writer_and_releases_on_exit(repository, capsys):
    path = ledger_path(repository, "example").parent / "ledger.lock"
    path.parent.mkdir(parents=True)
    command = [
        "--repository",
        str(repository),
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
        "Retain evidence.",
        "--commitment",
        "Retain evidence.",
        "--action",
        "Record.",
        "--impact",
        "No change.",
    ]
    with path.open("a") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(command) == 2
        assert read_states(repository, "example") == ()
    assert main(command) == 0
    assert len(read_states(repository, "example")) == 1
    capsys.readouterr()


@pytest.mark.parametrize("status", ["Accepted", "Proposed"])
def test_specification_resolution_checks_its_required_decision(repository, status):
    approve_change(repository, "follow-up")
    spec = repository / "changes/follow-up/specs/behavior.toml"
    spec.write_text(
        spec.read_text().replace(
            "plan = ", 'decisions = ["docs/decisions/ADP-follow-up.md"]\nplan = '
        )
    )
    decision = repository / "docs/decisions/ADP-follow-up.md"
    decision.parent.mkdir(parents=True)
    decision.write_text(f"# Decision\nStatus: {status}\n")
    event = _discovered()
    append_event(repository, event)
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=ResolutionKind.RESOLVED_IN_SPECIFICATION,
            targets=("changes/follow-up/specs/behavior.toml",),
            reason="Named authority.",
            implemented=True,
        ),
    )
    if status == "Accepted":
        assert reconciliation_summary(repository, ("example",))["deviation_count"] == 1
    else:
        with pytest.raises(DeviationError, match="decision is not accepted"):
            reconciliation_summary(repository, ("example",))


@pytest.mark.parametrize(
    "kind",
    [
        ResolutionKind.DEFERRED,
        ResolutionKind.RESOLVED_IN_SPECIFICATION,
        ResolutionKind.RESOLVED_IN_DECISION,
    ],
)
def test_resolution_uses_declared_change_and_decision_roots(repository, kind, capsys):
    (repository / "signetum.toml").write_text(
        MANIFEST.replace("changes/*", "work-items/*").replace(
            'decisions = "docs/decisions"', 'decisions = "governance"'
        )
    )
    (repository / "work-items/example").mkdir(parents=True)
    approve_change(repository, "follow-up")
    old = repository / "changes/follow-up"
    old.rename(repository / "work-items/follow-up")
    package = repository / "work-items/follow-up"
    for relative in ("specs/behavior.toml", "plans/behavior.md"):
        path = package / relative
        path.write_text(path.read_text().replace("changes/follow-up/", "work-items/follow-up/"))
    decision = repository / "governance/ADP-follow-up.md"
    decision.parent.mkdir()
    decision.write_text("# Decision\nStatus: Accepted\n")
    spec = package / "specs/behavior.toml"
    spec.write_text(
        spec.read_text().replace("plan = ", 'decisions = ["governance/ADP-follow-up.md"]\nplan = ')
    )
    append_event(repository, _discovered())
    target = (
        "governance/ADP-follow-up.md"
        if kind == ResolutionKind.RESOLVED_IN_DECISION
        else "work-items/follow-up/specs/behavior.toml"
    )
    command = [
        "--repository",
        str(repository),
        "resolve",
        "--change",
        "example",
        "--id",
        "DEV-001",
        "--member",
        "impl/example",
        "--resolution",
        kind.value,
        "--target",
        target,
        "--reason",
        "Declared authority.",
    ]
    if kind != ResolutionKind.DEFERRED:
        command.append("--implemented")
    assert main(command) == 0
    assert reconciliation_summary(repository, ("example",))["deviation_count"] == 1
    capsys.readouterr()


def test_a_mention_of_accepted_does_not_approve_a_proposed_decision(repository):
    target = repository / "docs/decisions/ADP-new.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Proposal\nStatus: Proposed\nHistorical note: Status: Accepted\n")
    event = _discovered()
    append_event(repository, event)
    append_event(
        repository,
        Resolved(
            id=event.id,
            change_id="example",
            member="impl/example",
            at=datetime.now(UTC),
            resolution=ResolutionKind.RESOLVED_IN_DECISION,
            targets=("docs/decisions/ADP-new.md",),
            reason="Still proposed.",
            implemented=False,
        ),
    )
    with pytest.raises(DeviationError, match="not accepted"):
        reconciliation_summary(repository, ("example",))


def test_portable_codec_preserves_existing_canonical_event_and_state_bytes():
    event = Discovered(
        id="stable",
        change_id="example",
        member="plan/example",
        at=datetime(2026, 10, 29, tzinfo=UTC),
        summary="Stable é",
        classification=DeviationClass.IMPLEMENTATION_CLARIFICATION,
        original_commitment="Keep behavior",
        action="Reuse owner",
        impact="None",
    )
    expected = (
        '{"event":"discovered","id":"stable","change_id":"example",'
        '"member":"plan/example","at":"2026-10-29T00:00:00Z","summary":"Stable é",'
        '"classification":"implementation_clarification","original_commitment":"Keep behavior",'
        '"action":"Reuse owner","impact":"None","source_commit":null}'
    )
    assert event_json(event) == expected
    assert event_json(DeviationState(discovered=event)) == (
        '{"discovered":' + expected + ',"resolution":null}'
    )
