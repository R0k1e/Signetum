"""Pure contracts for ordering, group coverage and result identity."""

import json
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from signetum.ci_partitions import (
    PartitionConfiguration,
    PartitionPlan,
    PartitionResult,
    combine,
    partition_snapshot,
)
from signetum.evidence.receipts import ArtifactIdentity, EvidenceIdentity
from signetum.pytest_scheduling import derive_weights, shared_file_groups
from signetum.pytest_scheduling import main as schedule_main
from signetum.test_scheduling import ordered_units, partition_units
from signetum.validation import (
    GateDeclaration,
    GraphContribution,
    ValidationShard,
    resolve_validation_graph,
)


@given(st.lists(st.integers(min_value=0, max_value=6), min_size=1, max_size=20))
def test_ordering_is_a_membership_preserving_whole_group_permutation(groups):
    units = tuple((str(g), str(n)) for n, g in enumerate(groups))
    ordered = ordered_units(units, {"1": 100.0})
    assert set(ordered) == {item for _, item in units}
    for group in set(groups):
        members = [item for unit, item in units if unit == str(group)]
        positions = [ordered.index(item) for item in members]
        assert positions == list(range(min(positions), max(positions) + 1))
        assert [ordered[p] for p in positions] == members


@pytest.mark.parametrize(
    "weights",
    [
        {"a": 0},
        {"a": -1},
        {"a": float("inf")},
        {"a": float("nan")},
        {"a": True},
        {"": 1},
        {"a": "bad"},
        [],
    ],
)
def test_invalid_weights_cannot_change_execution(weights):
    with pytest.raises(ValueError):
        ordered_units((), weights)


def test_partitions_preserve_transitive_shared_groups_and_exact_coverage():
    parts = partition_units(("a", "b", "c", "d", "e"), 2, {"e": 20}, (("a", "b"), ("b", "c")))
    assert set(parts[0]) | set(parts[1]) == {"a", "b", "c", "d", "e"}
    assert not set(parts[0]) & set(parts[1])
    assert any({"a", "b", "c"} <= set(p) for p in parts)
    assert ordered_units((("light", "a"), ("heavy", "b")), {"heavy": 20}) == ("b", "a")


@pytest.mark.parametrize(
    "files,count,groups",
    [
        (("a", "a"), 1, ()),
        (("a",), 0, ()),
        (("a",), 2, ()),
        (("a", "b"), 2, (("a", "b"),)),
        (("a",), 1, (("foreign",),)),
        (("a",), 1, ((),)),
    ],
)
def test_invalid_partition_declarations_refuse(files, count, groups):
    with pytest.raises(ValueError):
        partition_units(files, count, {}, groups)


def test_pytest_groups_are_read_without_import_and_dynamic_names_refuse():
    shared = b'GROUP="shared"\n@pytest.mark.xdist_group(GROUP)\ndef test_x(): pass\n'
    groups = shared_file_groups(
        {
            "tests/a.py": shared,
            "tests/b.py": shared,
            "tests/c.py": b'@pytest.mark.xdist_group(name="other")\ndef test_y(): pass\n',
        }
    )
    assert ("tests/a.py", "tests/b.py") in groups
    assert shared_file_groups({"x.py": b"@pytest.mark.xdist_group()\ndef test_x():pass\n"}) == (
        ("x.py",),
    )
    with pytest.raises(ValueError, match="unresolved"):
        shared_file_groups({"bad.py": b"@pytest.mark.xdist_group(dynamic())\ndef test_x(): pass\n"})


@pytest.fixture
def plan():
    artifact = ArtifactIdentity.from_bytes("signetum.toml", b"configuration")
    identity = EvidenceIdentity(
        "1" * 40, "2" * 40, None, artifact, (), "sha256:" + "0" * 64, (), ()
    )
    return PartitionPlan(
        schema_version=1,
        run_id="current-run",
        identity=identity,
        configuration=artifact,
        shard="unit",
        command=("python", "-m", "pytest", "tests"),
        argument_index=3,
        partitions=(("tests/a.py",), ("tests/b.py",)),
    )


def results(plan):
    return tuple(
        PartitionResult(
            schema_version=1,
            plan_digest=plan.digest,
            identity=plan.identity,
            index=n,
            files=files,
            command=(*plan.command[:3], *files),
            passed=True,
            recovered=False,
        )
        for n, files in enumerate(plan.partitions)
    )


def test_complete_partition_evidence_is_diagnostic_only(plan):
    answer = combine(plan, results(plan), job_statuses=("success", "success"))
    assert answer["authority"] == "ci_diagnostic_only" and answer["files"] == 2


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "duplicate",
        "identity",
        "plan",
        "failed",
        "recovered",
        "files",
        "command",
        "overlap",
        "empty",
    ],
)
def test_incomplete_or_mismatched_partition_results_never_aggregate_success(plan, damage):
    items = results(plan)
    if damage == "missing":
        items = items[:1]
    elif damage == "duplicate":
        items = (items[0], items[0])
    elif damage == "overlap":
        plan = replace(plan, partitions=(("tests/a.py",), ("tests/a.py",)))
    elif damage == "empty":
        plan = replace(plan, partitions=((), ("tests/b.py",)))
    else:
        fields = {
            "identity": {"identity": replace(plan.identity, commit="3" * 40)},
            "plan": {"plan_digest": "wrong"},
            "failed": {"passed": False},
            "recovered": {"recovered": True},
            "files": {"files": ("other",)},
            "command": {"command": ("other",)},
        }[damage]
        items = (replace(items[0], **fields), items[1])
    with pytest.raises(ValueError):
        combine(plan, items, job_statuses=("success", "success"))


@pytest.mark.parametrize(
    "states",
    [(), ("success",), ("success", "cancelled"), ("failure", "success"), ("success", "skipped")],
)
def test_ci_job_conclusions_cannot_be_replaced_by_present_artifacts(plan, states):
    with pytest.raises(ValueError, match="CI jobs"):
        combine(plan, results(plan), job_statuses=states)


@pytest.mark.parametrize(
    "damage",
    [None, "input", "index", "shard", "patterns", "group", "root", "notfinal", "world", "ratchet"],
)
def test_partition_snapshot_validates_configuration_without_repository_effects(damage):
    config = PartitionConfiguration(
        schema_version=1,
        shard="test:check",
        roots=("checks",),
        patterns=("checks/test_*.py",),
        argument_index=1,
        slices=2,
        framework="pytest",
    )
    sources = {
        "checks/test_a.py": b'@pytest.mark.xdist_group("shared")\ndef test_a():pass\n',
        "checks/test_b.py": b"def test_b():pass\n",
    }
    shard = ValidationShard("test:check", ("runner", "checks"))
    declared = ("partitions.json",)
    if damage == "input":
        declared = ()
    elif damage == "index":
        config = replace(config, argument_index=20)
    elif damage == "shard":
        config = replace(config, shard="test:missing")
    elif damage == "patterns":
        config = replace(config, patterns=("does-not-exist",))
    elif damage == "group":
        sources["checks/test_a.py"] = b"@pytest.mark.xdist_group(dynamic())\ndef test_a():pass\n"
    elif damage == "world":
        shard = replace(shard, evidence="world")
    elif damage == "ratchet":
        shard = replace(shard, ratchet_command=("measure",))
    graph = resolve_validation_graph(
        (
            GraphContribution(
                "fixture",
                (shard,),
                (GateDeclaration("final", (shard.name,) if damage != "notfinal" else ()),),
            ),
        )
    )

    def plan():
        chosen = replace(config, roots=("../outside",)) if damage == "root" else config
        return partition_snapshot(
            chosen, graph, sources, configuration_path="partitions.json", declared_inputs=declared
        )

    if damage is None:
        assert {p for lane in plan() for p in lane} == set(sources)
    else:
        with pytest.raises(ValueError):
            plan()


def test_duration_hints_reuse_logs_and_preserve_group_or_file_identity():
    log = (
        "noise\n2.00s setup tests/a.py::test_x@shared\n"
        "3.00s call tests/a.py::test_x@shared\n"
        "1.00s teardown tests/b.py::test_y[user@example]\n"
        "0.00s call tests/zero.py::test_zero\n"
    )
    assert derive_weights(log) == {"shared": 5.0, "tests/b.py::test_y[user@example]": 1.0}
    assert derive_weights(log, by_file=True) == {"tests/a.py": 5.0, "tests/b.py": 1.0}
    assert derive_weights(log, minimum_seconds=2) == {"shared": 5.0}
    with pytest.raises(ValueError):
        derive_weights(log, minimum_seconds=-1)
    with pytest.raises(ValueError):
        shared_file_groups({"bad.py": b"broken("})


def test_schedule_utility_derives_without_overwriting_or_fabricating_observations(tmp_path, capsys):
    log = tmp_path / "run.log"
    output = tmp_path / "weights.json"
    log.write_text("1.00s call tests/a.py::test_a\n")
    assert schedule_main(["--log", str(log), "--output", str(output), "--by-file"]) == 0
    assert json.loads(output.read_text()) == {"tests/a.py": 1.0}
    assert len(capsys.readouterr().out.splitlines()) == 1
    assert schedule_main(["--log", str(log), "--output", str(output)]) == 4
    assert json.loads(capsys.readouterr().out)["status"] == "infrastructure_error"
    log.write_text("no duration data")
    missing = tmp_path / "missing.json"
    assert schedule_main(["--log", str(log), "--output", str(missing)]) == 2
    assert not missing.exists()
    capsys.readouterr()
    assert schedule_main([]) == 2
    assert json.loads(capsys.readouterr().out)["expected"]
