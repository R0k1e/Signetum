"""Behavior tests for the bootstrap batch-admission authority."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from shutil import which
from typing import Literal

import pytest
from change_fixtures import approve_change as _approve_change
from change_fixtures import commit_approval
from pydantic import JsonValue

import signetum.lifecycle as lifecycle
from signetum.validation import command_digest
from signetum.validation.execution import ShardExecution, build_evidence_identity
from signetum.workspaces import WorkspaceRecord, write_record


def _load_module():
    return lifecycle


def _git(repository: Path, *arguments: str) -> str:
    executable = which("git")
    if executable is None:
        raise RuntimeError("git executable is unavailable")
    return subprocess.run(  # nosec B603
        (executable, "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


MANIFEST = """schema_version = 2

[signetum]
protocol = 2
template_version = "0.2.0"

[repository]
architecture = "docs/ARCHITECTURE.md"
specifications = "changes/*/specs/*.toml"
plans = "changes/*/plans/*.md"
decisions = "docs/decisions"

[[impact.rules]]
name = "everything"
paths = ["**"]
shards = ["repo:check"]

[[impact.rules]]
name = "governance"
paths = ["docs/**"]
requires_final = true

[validation]
member_required = ["repo:check"]

[[validation.shards]]
name = "repo:check"
command = ["true"]

[[validation.gates]]
name = "member"
shards = ["repo:check"]

[[validation.gates]]
name = "final"
shards = ["repo:check"]
[[validation.gates]]
name = "prepare"
shards = ["repo:check"]

[[validation.gates]]
name = "batch"
shards = ["repo:check"]

"""

MEMBER_COMMAND = ("true",)


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Signetum Tests")
    _git(path, "config", "user.email", "signetum@example.invalid")
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    (path / "signetum.toml").write_text(MANIFEST, encoding="utf-8")
    policy = path / ".agents/repo-dev/repo.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("delivery:\n  branch: main\n")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "seed")
    remote = path.parent / (path.name + ".git")
    remote.mkdir()
    _git(remote, "init", "--bare")
    _git(path, "remote", "add", "origin", str(remote))
    _git(path, "push", "origin", "main")
    return path


def _record(
    worktree: Path, branch: str, base: str, kind: Literal["member", "batch"] = "member"
) -> None:
    """Record the base a test workspace was cut from, as workspace-open would."""

    write_record(
        lifecycle._state_root(worktree),
        WorkspaceRecord(schema_version=1, branch=branch, base=base, kind=kind),
    )


def _evidence_receipt(
    member: Path, name: str, *, gate: str, tree: str, commands: tuple[tuple[str, ...], ...]
) -> Path:
    """Write one durable lifecycle receipt proving the given shard commands."""

    manifest = lifecycle.load_manifest(member / "signetum.toml")
    base = lifecycle._recorded_base(member)
    selection = lifecycle._selection(member, base, manifest)
    shards, _ = lifecycle._member_shards(manifest, selection)
    graph, inputs = lifecycle._runtime_validation(
        manifest, member_shards=shards if gate == "member" else None
    )
    identity = build_evidence_identity(
        graph, replace(inputs, base=base), lifecycle.RepositoryValidationAdapter(member)
    )
    evidence = {
        "schema_version": 3,
        "protocol": "reposeal.validation-evidence@3",
        "schema_digest": manifest.signetum.evidence_schema_digest,
        "identity": {**asdict(identity), "tree": tree},
        "selection": None,
        "execution": {
            "gates": [gate],
            "shards": [
                {
                    "name": f"repo:proven-{index}",
                    "command_digest": command_digest(command),
                    "evidence": "tree",
                    "status": "passed",
                    "observed_at": None,
                    "waivers": [],
                    "findings": [],
                }
                for index, command in enumerate(commands)
            ],
            "external_obligations": [],
        },
        "completeness": {
            "member": gate == "member",
            "final": gate == "final",
            "required_shards": [f"repo:proven-{index}" for index in range(len(commands))],
            "world_shards": [],
        },
        "provenance": {"stable_patch_id": None},
        "extensions": {},
        "valid": True,
    }
    path = lifecycle._receipt_root(member) / name
    path.write_text(
        json.dumps({"kind": gate, "valid": True, "evidence": evidence}), encoding="utf-8"
    )
    return path


def test_delivery_branch_names_are_refused() -> None:
    module = _load_module()

    assert {"main", "master", "product"}.isdisjoint({"batch/signetum-v2"})
    assert module.AdmissionError


@pytest.mark.parametrize("return_code", [0, 1])
def test_ancestor_query_has_two_valid_outcomes(
    monkeypatch, tmp_path: Path, return_code: int
) -> None:
    module = _load_module()

    class Completed:
        stderr = ""

        def __init__(self, code: int) -> None:
            self.returncode = code

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: Completed(return_code))

    assert module._is_ancestor(tmp_path, "member", "batch") is (return_code == 0)


def test_manifest_gate_retains_commands_and_dependency_order(tmp_path: Path) -> None:
    module = _load_module()
    manifest = module.load_manifest(Path(__file__).resolve().parents[1] / "signetum.toml")
    graph, _ = module._runtime_validation(manifest)
    shards = {shard.name: shard.command for shard in graph.shards}
    declared_gate = next(gate for gate in manifest.validation.gates if gate.name == "member")
    declared_commands = {shard.name: shard.command for shard in manifest.validation.shards}
    assert set(graph.gate("member").shards) == set(declared_gate.shards)
    assert shards == declared_commands
    order = graph.execution_order("member")
    for shard in graph.shards:
        if shard.name in order:
            assert all(
                order.index(dependency) < order.index(shard.name) for dependency in shard.requires
            )


def test_delivery_provenance_uses_actual_package_plans_and_named_member(tmp_path):
    member, batch, base = _member_and_batch(tmp_path)
    _approve_change(member)
    _git(member, "add", ".")
    _git(member, "commit", "-m", "approve package")
    (member / "implemented.txt").write_text("behavior")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "implement\n\nDelivers: invented/plan.md")
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    members, plans = lifecycle._delivery_provenance(batch, base, _git(batch, "rev-parse", "HEAD"))
    assert plans == ["changes/example/plans/behavior.md"]
    assert members[0]["branch"] == "impl/member"
    assert members[0]["original"] == _git(member, "rev-parse", "HEAD")
    assert members[0]["plan"] == plans[0]


def test_admission_records_member_and_final_numbers_only_accepted_decisions(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "repository")
    legacy = repository / "docs/decisions/ADP-historical.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("# Historical\n\nStatus: Accepted\n")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "record historical accepted decision")

    base = _git(repository, "rev-parse", "HEAD")
    member = tmp_path / "member"
    batch = tmp_path / "batch"
    _git(repository, "worktree", "add", "-b", "impl/member", str(member), base)
    _git(repository, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(member, "impl/member", base)
    _record(batch, "batch/test", base, "batch")
    commit_approval(member)
    decision = member / "docs/decisions/ADP-zebra.md"
    decision.parent.mkdir(parents=True, exist_ok=True)
    decision.write_text(
        "# Zebra\n\nStatus: Accepted\nSupersedes: ADP-0001-yak.md\nSuperseded by: None\n"
        "\nSee ADP-zebra.md.\n",
        encoding="utf-8",
    )
    (member / "docs/decisions/ADP-0001-yak.md").write_text(
        "# Yak\n\nStatus: Accepted\nSupersedes: None\nSuperseded by: None\n",
        encoding="utf-8",
    )
    plan = "changes/example/plans/member.md"
    (member / "reference.md").write_text(
        "Decision: docs/decisions/ADP-zebra.md\n", encoding="utf-8"
    )
    _git(member, "add", ".")
    _git(member, "commit", "-m", f"deliver member\n\nDelivers: {plan}")
    member_tip = _git(member, "rev-parse", "HEAD")
    _evidence_receipt(
        member,
        "member-lifecycle-ready.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )

    result = lifecycle.admit(batch, (member,))

    assert result["status"] == "admitted"
    assert (batch / "docs/decisions/ADP-zebra.md").is_file()
    assert (member / "docs/decisions/ADP-zebra.md").is_file()
    admitted_members = result["admitted"]
    assert isinstance(admitted_members, list)
    admitted = admitted_members[0]
    assert admitted["original"] == member_tip
    assert admitted["ready_evidence"] == "member-lifecycle-ready.json"
    assert admitted["plan"] == ["changes/example/plans/behavior.md"]
    final = lifecycle.validate(batch, "final")
    formal = batch / "docs/decisions/ADP-0002-zebra.md"
    assert formal.is_file()
    assert (batch / "docs/decisions/ADP-historical.md").read_text() == legacy.read_text()
    assert final["source"] == _git(batch, "rev-parse", "HEAD")
    assert final["numbered"] == [
        {
            "proposal": "docs/decisions/ADP-zebra.md",
            "formal": "docs/decisions/ADP-0002-zebra.md",
        }
    ]
    assert (
        "Superseded by: ADP-0002-zebra.md" in (batch / "docs/decisions/ADP-0001-yak.md").read_text()
    )
    assert "ADP-0002-zebra.md" in (batch / "reference.md").read_text()
    numbered_tip = final["source"]
    repeated_final = lifecycle.validate(batch, "final")
    assert repeated_final["numbered"] == []
    assert repeated_final["source"] == numbered_tip
    repeated = lifecycle.admit(batch, (member,))
    assert repeated["admitted"] == []
    unchanged_members = repeated["unchanged"]
    assert isinstance(unchanged_members, list)
    assert unchanged_members[0]["original"] == member_tip

    (member / "incremental.txt").write_text("second admission\n", encoding="utf-8")
    _git(member, "add", ".")
    _git(member, "commit", "-m", f"extend member\n\nDelivers: {plan}")
    advanced_tip = _git(member, "rev-parse", "HEAD")
    _evidence_receipt(
        member,
        "member-lifecycle-advanced.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )
    incremental = lifecycle.admit(batch, (member,))
    incremental_members = incremental["admitted"]
    assert isinstance(incremental_members, list)
    assert incremental_members[0]["original"] == advanced_tip
    assert incremental_members[0]["admission_commit"] != admitted["admission_commit"]


def test_delivery_refuses_numbering_bound_to_another_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    monkeypatch.setattr(lifecycle, "_require_clean", lambda path: None)
    monkeypatch.setattr(lifecycle, "_recorded_base", lambda path, branch=None: "older-base")
    monkeypatch.setattr(
        lifecycle,
        "_git",
        lambda repository, *arguments, **kwargs: "tip" if repository == source else "approved-base",
    )

    with pytest.raises(lifecycle.AdmissionError, match="recorded batch base differs"):
        lifecycle.batch_deliver(source, target, "approved-base", "tip")


def test_final_refuses_proposal_decisions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository")
    proposal = repository / "docs/decisions/ADP-unresolved.md"
    proposal.parent.mkdir(parents=True)
    proposal.write_text("# unresolved\n\nStatus: Proposed\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "add proposal")
    _record(repository, "main", _git(repository, "rev-parse", "HEAD"), "batch")
    with pytest.raises(lifecycle.AdmissionError, match="proposal decision"):
        lifecycle.validate(repository, "final")


def _member_and_batch(
    tmp_path: Path, *, path: str = "src/feature.txt", approved: bool = False
) -> tuple[Path, Path, str]:
    repository = _repository(tmp_path / "repository")
    base = _git(repository, "rev-parse", "HEAD")
    member = tmp_path / "member"
    batch = tmp_path / "batch"
    _git(repository, "worktree", "add", "-b", "impl/member", str(member), base)
    _git(repository, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(member, "impl/member", base)
    _record(batch, "batch/test", base, "batch")
    if approved:
        commit_approval(member)
    target = member / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("work\n", encoding="utf-8")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "deliver member\n\nDelivers: changes/example/plans/member.md")
    return member, batch, base


def test_a_completed_final_gate_satisfies_member_admission(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    _evidence_receipt(
        member,
        "final-lifecycle-frozen.json",
        gate="final",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND, ("extra",)),
    )

    result = lifecycle.admit(batch, (member,))

    admitted = result["admitted"]
    assert isinstance(admitted, list)
    assert admitted[0]["ready_evidence"] == "final-lifecycle-frozen.json"


def test_final_review_projects_member_and_final_recovered_defects(tmp_path, monkeypatch):
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    defect: dict[str, JsonValue] = {
        "node_id": "tests/test_contract.py::test_contract",
        "first_failure": [{"phase": "call", "outcome": "failed", "diagnostic": "first contention"}],
    }
    monkeypatch.setattr(
        lifecycle.RepositoryValidationAdapter,
        "run_shard",
        lambda self, shard: ShardExecution(True, recovered=(defect,)),
    )
    ready = lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    final = lifecycle.validate(batch, "final")
    review = final["delivery_review"]
    assert isinstance(review, dict)
    defects = review["recovered_flake_defects"]
    assert len(defects) == 2
    assert {item["source_gate"] for item in defects} == {"member", "final"}
    assert any(item["source_receipt"] == ready["receipt"] for item in defects)
    assert all("first contention" in str(item["first_failure"]) for item in defects)


@pytest.mark.parametrize("damage", ["missing", "altered", "different-tip"])
def test_final_refuses_invalid_provenance_named_member_evidence(tmp_path, damage):
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    ready = lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    receipt = ready["receipt"]
    assert isinstance(receipt, str)
    path = Path(receipt)
    if damage == "missing":
        path.unlink()
    else:
        payload = json.loads(path.read_text())
        if damage == "altered":
            payload["evidence"]["extensions"]["unexpected"] = "changed"
        else:
            payload["evidence"]["identity"]["commit"] = "f" * 40
        path.write_text(json.dumps(payload))
    with pytest.raises(lifecycle.AdmissionError, match="admitted member evidence"):
        lifecycle.validate(batch, "final")


def test_final_evidence_cannot_bypass_repeated_member_recovery_policy(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    path = _evidence_receipt(
        member,
        "final-lifecycle-frozen.json",
        gate="final",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )
    payload = json.loads(path.read_text())
    payload["evidence"]["extensions"] = {
        "recovered_flake_defects": [{"shard": "repo:check", "node_id": "test_example"}]
    }
    path.write_text(json.dumps(payload))
    for index in (1, 2):
        prior = json.loads(json.dumps(payload["evidence"]))
        prior["identity"]["commit"] = str(index) * 40
        path.with_name(f"member-prior-{index}.json").write_text(json.dumps(prior))
    before = _git(batch, "rev-parse", "HEAD")
    with pytest.raises(lifecycle.ValidationExecutionError, match="repeated recovered"):
        lifecycle.admit(batch, (member,))
    assert _git(batch, "rev-parse", "HEAD") == before


def test_reworded_member_requires_fresh_exact_tip_evidence(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    tree = _git(member, "rev-parse", "HEAD^{tree}")
    _evidence_receipt(
        member,
        "member-lifecycle-ready.json",
        gate="member",
        tree=tree,
        commands=(MEMBER_COMMAND,),
    )
    original = _git(member, "rev-parse", "HEAD")
    _git(member, "commit", "--amend", "-m", "reworded\n\nDelivers: changes/example/plans/member.md")
    amended = _git(member, "rev-parse", "HEAD")

    assert amended != original
    assert _git(member, "rev-parse", "HEAD^{tree}") == tree

    with pytest.raises(lifecycle.AdmissionError, match="no evidence proving its selected"):
        lifecycle.admit(batch, (member,))


def test_evidence_proving_the_wrong_commands_is_not_admission(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    _evidence_receipt(
        member,
        "member-lifecycle-unrelated.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(("something", "else"),),
    )

    with pytest.raises(lifecycle.AdmissionError, match="no evidence proving its selected"):
        lifecycle.admit(batch, (member,))


def test_requires_final_does_not_replace_member_evidence(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path, path="docs/note.md", approved=True)
    with pytest.raises(lifecycle.AdmissionError, match="no evidence proving its selected"):
        lifecycle.admit(batch, (member,))


@pytest.mark.parametrize(
    "field", ["commit", "base", "configuration", "profiles", "graph", "tools", "lockfiles"]
)
def test_admission_refuses_different_validation_inputs(tmp_path: Path, field: str) -> None:
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    path = _evidence_receipt(
        member,
        "member-lifecycle-stale.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )
    payload = json.loads(path.read_text())
    identity = payload["evidence"]["identity"]
    replacements = {
        "commit": "a" * 40,
        "base": "b" * 40,
        "configuration": {"path": "signetum.toml", "digest": "sha256:" + "1" * 64},
        "profiles": ["different@1"],
        "graph": "sha256:" + "2" * 64,
        "tools": [{"name": "other", "identity": "1"}],
        "lockfiles": [{"path": "other.lock", "digest": "sha256:" + "3" * 64}],
    }
    identity[field] = replacements[field]
    path.write_text(json.dumps(payload))
    with pytest.raises(lifecycle.AdmissionError, match="no evidence proving its selected"):
        lifecycle.admit(batch, (member,))


def test_a_failing_gate_is_refused_as_one_json_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failing gate is an ordinary outcome, never an unhandled traceback."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise lifecycle.ValidationExecutionError("validation shard failed: engine:ruff")

    monkeypatch.setattr(lifecycle, "validate", refuse)

    assert lifecycle.main(["final"]) == 3


def _without_change_packages(worktree: Path) -> None:
    """Leave a tree whose declared specification authority matches nothing."""

    for path in worktree.glob("changes/*/specs/*.toml"):
        path.unlink()


def test_member_evidence_cannot_replace_a_removed_specification(tmp_path: Path) -> None:
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    _without_change_packages(member)
    _git(member, "commit", "-a", "--allow-empty", "-m", "render without a change package")
    _evidence_receipt(
        member,
        "member-lifecycle-ready.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )

    with pytest.raises(lifecycle.AdmissionError, match="not implementation-authorized"):
        lifecycle.admit(batch, (member,))


def test_an_incomplete_change_is_refused_even_without_a_trailer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository")
    base = _git(repository, "rev-parse", "HEAD")
    member = tmp_path / "member"
    batch = tmp_path / "batch"
    _git(repository, "worktree", "add", "-b", "impl/member", str(member), base)
    _git(repository, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(member, "impl/member", base)
    _record(batch, "batch/test", base, "batch")
    specification = member / "changes/example/specs/first.toml"
    specification.parent.mkdir(parents=True)
    specification.write_text("[specification]\n", encoding="utf-8")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "record a change package without naming it")

    with pytest.raises(lifecycle.AdmissionError, match="package is unavailable or invalid"):
        lifecycle.admit(batch, (member,))


def test_both_gates_run_the_declared_traceability_authority() -> None:
    """A declared authority which no gate runs is feedback, not a contract."""
    manifest = lifecycle.load_manifest(Path(__file__).resolve().parents[1] / "signetum.toml")
    shards = {shard.name: shard for shard in manifest.validation.shards}
    authority = next(
        name
        for name, shard in shards.items()
        if shard.command[-3:] == ("check", "traceability", "--repository")
        or "traceability" in shard.command
    )

    for gate in manifest.validation.gates:
        if gate.name not in {"member", "final"}:
            continue
        assert authority in gate.shards, f"{gate.name} does not run {authority}"


def test_real_failing_member_check_keeps_stdout_machine_readable(tmp_path, monkeypatch, capsys):
    repository = _repository(tmp_path / "repository")
    script = repository / "check.py"
    script.write_text(
        "import sys\nprint('check output')\nprint('check error', file=sys.stderr)\nsys.exit(1)\n"
    )
    manifest = repository / "signetum.toml"
    manifest.write_text(
        manifest.read_text().replace(
            'command = ["true"]', "command = " + json.dumps([sys.executable, "check.py"])
        )
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "declare failing check")
    base = _git(repository, "rev-parse", "HEAD")
    commit_approval(repository)
    (repository / "seed.txt").write_text("member change")
    _git(repository, "commit", "-am", "change behavior")
    _record(repository, "main", base)
    monkeypatch.chdir(repository)

    assert lifecycle.main(["ready"]) == 3
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "failed"
    assert result["operation"] == "ready"
    assert "check output" in captured.err
    assert "check error" in captured.err
    assert "check output" in Path(result["log"]).read_text()
    assert "check error" in Path(result["log"]).read_text()
    assert list(lifecycle._receipt_root(repository).glob("member-*.json")) == []


def test_admission_does_not_accept_a_proposed_decision(tmp_path):
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    decision = member / "docs/decisions/ADP-unapproved.md"
    decision.parent.mkdir(parents=True, exist_ok=True)
    decision.write_text("# Unapproved\n\nStatus: Proposed\n")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "propose a decision")
    _evidence_receipt(
        member,
        "member-lifecycle-proposal.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )
    lifecycle.admit(batch, (member,))
    with pytest.raises(lifecycle.AdmissionError, match="proposal decisions"):
        lifecycle.validate(batch, "final")
    assert (batch / "docs/decisions/ADP-unapproved.md").read_text() == decision.read_text()


def test_numbering_preserves_other_supersession_edges(tmp_path):
    root = tmp_path / "decisions"
    root.mkdir()
    old = root / "old.md"
    old.write_text("# Old\nSuperseded by: earlier.md\n")
    new = root / "new.md"
    new.write_text("# New\nSupersedes: old.md\n")
    lifecycle._record_supersession(tmp_path, Path("decisions/new.md"))
    assert old.read_text() == "# Old\nSuperseded by: earlier.md, new.md\n"


def test_actual_change_paths_supply_review_and_plans_without_a_trailer(tmp_path):
    member, batch, _ = _member_and_batch(tmp_path)
    _approve_change(member)
    _git(member, "add", ".")
    _git(member, "commit", "-m", "approve change")
    (member / "implemented.txt").write_text("approved behavior")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "implement without a trailer")
    lifecycle.validate(member, "member")
    result = lifecycle.admit(batch, (member,))
    admitted = result["admitted"]
    assert isinstance(admitted, list)
    assert admitted[0]["plan"] == ["changes/example/plans/behavior.md"]
    final = lifecycle.validate(batch, "final")
    review = final["delivery_review"]
    assert isinstance(review, dict)
    assert review["approvals"][0]["change_id"] == "example"
    assert review["previously_delivered"] == []


def test_member_with_only_an_approved_package_is_plan_stage(tmp_path):
    member, _, _ = _member_and_batch(tmp_path)
    _approve_change(member)
    _git(member, "add", ".")
    _git(member, "commit", "-m", "approve the package only")
    with pytest.raises(lifecycle.AdmissionError, match="plan stage"):
        lifecycle.validate(member, "member")


def test_member_refuses_an_unapproved_change_before_executing_checks(tmp_path):
    member, _, _ = _member_and_batch(tmp_path)
    _approve_change(member)
    spec = member / "changes/example/specs/behavior.toml"
    spec.write_text(spec.read_text().replace('status = "approved"', 'status = "draft"'))
    _git(member, "add", ".")
    _git(member, "commit", "-m", "draft a package")
    (member / "implemented.txt").write_text("unauthorized")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "attempt implementation")
    with pytest.raises(lifecycle.AdmissionError, match="implementation-authorized"):
        lifecycle.validate(member, "member")
    assert list(lifecycle._receipt_root(member).glob("member-*.json")) == []


def test_final_refuses_rewriting_previously_delivered_requirements(tmp_path):
    repository = _repository(tmp_path / "repository")
    _approve_change(repository, "old")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "delivered old package")
    base = _git(repository, "rev-parse", "HEAD")
    batch = tmp_path / "batch"
    _git(repository, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(batch, "batch/test", base, "batch")
    spec = batch / "changes/old/specs/behavior.toml"
    spec.write_text(spec.read_text().replace("declared member check passes", "scope is reduced"))
    _git(batch, "commit", "-am", "rewrite delivered promise")
    with pytest.raises(lifecycle.AdmissionError, match="delivered commitments"):
        lifecycle.validate(batch, "final")


def test_final_lists_previous_plan_edits_without_reopening_old_approval(tmp_path):
    repository = _repository(tmp_path / "repository")
    _approve_change(repository, "old")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "delivered old package")
    base = _git(repository, "rev-parse", "HEAD")
    batch = tmp_path / "batch"
    _git(repository, "worktree", "add", "-b", "batch/test", str(batch), base)
    _record(batch, "batch/test", base, "batch")
    plan = batch / "changes/old/plans/behavior.md"
    plan.write_text(plan.read_text() + "\nHistorical execution clarification.\n")
    _git(batch, "commit", "-am", "clarify historical execution")
    final = lifecycle.validate(batch, "final")
    review = final["delivery_review"]
    assert isinstance(review, dict)
    assert review["approvals"] == []
    assert review["previously_delivered"] == [
        {
            "change_id": "old",
            "paths": ["changes/old/plans/behavior.md"],
        }
    ]


def test_an_approved_change_cannot_continue_in_a_second_member_workspace(tmp_path):
    member, _, base = _member_and_batch(tmp_path)
    _approve_change(member)
    _git(member, "add", ".")
    _git(member, "commit", "-m", "approve package")
    (member / "implemented.txt").write_text("behavior")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "implement")
    lifecycle.validate(member, "member")
    other = tmp_path / "second"
    _git(member, "worktree", "add", "-b", "impl/second", str(other), "HEAD")
    _record(other, "impl/second", base)
    with pytest.raises(lifecycle.AdmissionError, match="already belongs to member impl/member"):
        lifecycle.validate(other, "member")


def test_ready_requires_accepted_decisions_before_implementation(tmp_path):
    member, _, _ = _member_and_batch(tmp_path)
    _approve_change(member)
    spec = member / "changes/example/specs/behavior.toml"
    spec.write_text(
        spec.read_text().replace("plan = ", 'decisions = ["docs/decisions/ADP-new.md"]\nplan = ')
    )
    decision = member / "docs/decisions/ADP-new.md"
    decision.parent.mkdir(parents=True, exist_ok=True)
    decision.write_text("# New\nStatus: Proposed\n")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "draft required decision")
    (member / "implemented.txt").write_text("unauthorized")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "attempt implementation")
    with pytest.raises(lifecycle.AdmissionError, match="requires an accepted decision"):
        lifecycle.validate(member, "member")


def test_change_scope_uses_the_declared_package_root(tmp_path):
    member, batch, _ = _member_and_batch(tmp_path)
    _approve_change(member)
    (member / "changes").rename(member / "work")
    manifest = member / "signetum.toml"
    manifest.write_text(manifest.read_text().replace('"changes/', '"work/'))
    spec = member / "work/example/specs/behavior.toml"
    spec.write_text(spec.read_text().replace('"changes/', '"work/'))
    plan = member / "work/example/plans/behavior.md"
    plan.write_text(plan.read_text().replace("changes/", "work/"))
    _git(member, "add", ".")
    _git(member, "commit", "-m", "approve package under declared root")
    (member / "implemented.txt").write_text("behavior")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "implement")
    lifecycle.validate(member, "member")
    admitted = lifecycle.admit(batch, (member,))["admitted"]
    assert isinstance(admitted, list)
    assert admitted[0]["plan"] == ["work/example/plans/behavior.md"]
    result = lifecycle.validate(batch, "final")["delivery_review"]
    assert isinstance(result, dict)
    assert result["approvals"][0]["change_id"] == "example"


def test_final_cannot_number_or_validate_a_member_workspace(tmp_path):
    member, _, _ = _member_and_batch(tmp_path, approved=True)
    with pytest.raises(lifecycle.AdmissionError, match="requires a registered batch"):
        lifecycle.validate(member, "final")


def test_ready_cannot_close_an_integration_batch_as_a_member(tmp_path):
    _, batch, _ = _member_and_batch(tmp_path, approved=True)
    (batch / "fixup.txt").write_text("batch change")
    _git(batch, "add", ".")
    _git(batch, "commit", "-m", "integration change")
    with pytest.raises(lifecycle.AdmissionError, match="requires a registered member"):
        lifecycle.validate(batch, "member")


def test_final_allocates_above_fresh_remote_decision_numbers(tmp_path):
    member, batch, _ = _member_and_batch(tmp_path, approved=True)
    decision = member / "docs/decisions/ADP-new.md"
    decision.parent.mkdir(parents=True)
    decision.write_text("# New\nStatus: Accepted\nSupersedes: None\nSuperseded by: None\n")
    _git(member, "add", ".")
    _git(member, "commit", "-m", "accept a decision")
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,))
    root = tmp_path / "repository"
    occupied = root / "docs/decisions/ADP-0099-published.md"
    occupied.parent.mkdir(parents=True)
    occupied.write_text("# Published\nStatus: Accepted\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "publish a new decision identity")
    _git(root, "push", "origin", "main")
    final = lifecycle.validate(batch, "final")
    assert final["numbered"] == [
        {
            "proposal": "docs/decisions/ADP-new.md",
            "formal": "docs/decisions/ADP-0100-new.md",
        }
    ]


def test_ready_and_admission_refuse_an_implementation_without_a_change_package(tmp_path):
    member, batch, _ = _member_and_batch(tmp_path)
    with pytest.raises(lifecycle.AdmissionError, match="approved change package"):
        lifecycle.validate(member, "member")
    _evidence_receipt(
        member,
        "member-lifecycle-unowned.json",
        gate="member",
        tree=_git(member, "rev-parse", "HEAD^{tree}"),
        commands=(MEMBER_COMMAND,),
    )
    before = _git(batch, "rev-parse", "HEAD")
    with pytest.raises(lifecycle.AdmissionError, match="approved change package"):
        lifecycle.admit(batch, (member,))
    assert _git(batch, "rev-parse", "HEAD") == before
