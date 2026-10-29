"""Pure contracts for reach, ordering, group coverage and result identity."""

import json
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from signetum.ci_partitions import PartitionPlan, PartitionResult, combine, create_plan
from signetum.evidence.receipts import ArtifactIdentity, EvidenceIdentity
from signetum.git import git_output
from signetum.pytest_scheduling import derive_weights, shared_file_groups
from signetum.python_selection import DynamicLoader, PythonSelection, dependent_units
from signetum.test_scheduling import ordered_units, partition_units

CONFIG = PythonSelection(
    schema_version=1, source_roots=("app",), unit_roots=("tests",), unit_shard="unit"
)
SOURCE = {
    "app/feature.py": b"def value(): return 1\n",
    "app/api.py": b"from feature import value\n",
    "tests/test_api.py": b"from api import value\n",
    "tests/test_other.py": b"import os\n",
}


@pytest.mark.parametrize("path", ["app/feature.py", "app/api.py", "tests/test_api.py"])
def test_transitive_reach_is_pure_and_includes_changed_tests(path):
    selected, reasons = dependent_units(SOURCE, (path,), CONFIG)
    assert selected == ("tests/test_api.py",)
    assert not reasons


def test_deleted_source_relative_imports_and_conftest_preserve_reach():
    files = {
        "app/pkg/__init__.py": b"",
        "app/pkg/use.py": b"from . import removed\n",
        "tests/test_api.py": b"from pkg.use import removed\n",
        "tests/conftest.py": b"",
    }
    assert dependent_units(files, ("app/pkg/removed.py",), CONFIG)[0] == ("tests/test_api.py",)
    assert dependent_units(files, ("tests/conftest.py",), CONFIG)[0] == ("tests/test_api.py",)


@pytest.mark.parametrize(
    "source",
    [
        b"import importlib\nimportlib.import_module(name)\n",
        b"from importlib import import_module as load\nload(name)\n",
        b"exec(code)\n",
        b"broken(\n",
    ],
)
def test_uncertain_reach_runs_the_whole_unit_corpus(source):
    selected, reasons = dependent_units(
        {**SOURCE, "app/dynamic.py": source}, ("app/feature.py",), CONFIG
    )
    assert selected == ("tests/test_api.py", "tests/test_other.py")
    assert reasons


def test_declared_dynamic_loader_and_literal_loader_are_edges():
    files = {**SOURCE, "app/api.py": b"import importlib\nimportlib.import_module(name)\n"}
    config = replace(CONFIG, dynamic_loaders=(DynamicLoader(module="api", imports=("feature",)),))
    assert dependent_units(files, ("app/feature.py",), config) == (("tests/test_api.py",), ())
    files["app/api.py"] = b'import importlib\nimportlib.import_module("feature")\n'
    assert dependent_units(files, ("app/feature.py",), CONFIG) == (("tests/test_api.py",), ())
    with pytest.raises(ValueError, match="absent module"):
        dependent_units(
            files,
            ("app/feature.py",),
            replace(
                CONFIG, dynamic_loaders=(DynamicLoader(module="missing", imports=("feature",)),)
            ),
        )


def test_ambiguous_names_are_not_guessed():
    files = {**SOURCE, "other/feature.py": b""}
    selected, reasons = dependent_units(
        files, ("app/feature.py",), replace(CONFIG, source_roots=("app", "other"))
    )
    assert len(selected) == 2 and reasons


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


@pytest.fixture
def configured_partition(local_repository):

    root, _ = local_repository
    (root / "checks").mkdir()
    (root / "checks/test_a.py").write_text(
        '@pytest.mark.xdist_group("shared")\ndef test_a():pass\n'
    )
    (root / "checks/test_b.py").write_text("def test_b():pass\n")
    config = {
        "schema_version": 1,
        "shard": "test:check",
        "roots": ["checks"],
        "patterns": ["checks/test_*.py"],
        "argument_index": 1,
        "slices": 2,
        "framework": "pytest",
    }
    path = root / "partitions.json"
    path.write_text(json.dumps(config))
    manifest = root / "signetum.toml"
    manifest.write_text(
        manifest.read_text().replace(
            'decisions = "docs/decisions"',
            'decisions = "docs/decisions"\nlockfiles=["partitions.json"]',
        )
    )
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "configure partitions")
    return root, path, config


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "input",
        "index",
        "shard",
        "dirty",
        "patterns",
        "group",
        "root",
        "notfinal",
        "world",
        "ratchet",
    ],
)
def test_partition_planning_validates_bound_configuration_before_execution(
    configured_partition, damage
):

    root, path, config = configured_partition
    manifest = root / "signetum.toml"
    if damage == "input":
        manifest.write_text(
            manifest.read_text().replace('lockfiles=["partitions.json"]', "lockfiles=[]")
        )
    elif damage == "index":
        config["argument_index"] = 20
    elif damage == "shard":
        config["shard"] = "missing"
    elif damage == "dirty":
        (root / "uncommitted").touch()
    elif damage == "patterns":
        config["patterns"] = ["does-not-exist"]
    elif damage == "group":
        (root / "checks/test_a.py").write_text(
            "@pytest.mark.xdist_group(dynamic())\ndef test_a():pass\n"
        )
    elif damage == "root":
        config["roots"] = ["../outside"]
    elif damage == "notfinal":
        config["shard"] = "test:prepare"
    elif damage == "world":
        config["shard"] = "world:check"
        manifest.write_text(
            manifest.read_text()
            + '\n[[validation.shards]]\nname="world:check"\ncommand=["true"]\nevidence="world"\n'
        )
    elif damage == "ratchet":
        manifest.write_text(
            manifest.read_text().replace(
                'name = "test:check"\ncommand',
                'name = "test:check"\nratchet_command=["true"]\ncommand',
            )
        )
    path.write_text(json.dumps(config))
    if damage != "dirty":
        git_output(root, "add", ".")
        git_output(root, "commit", "--allow-empty", "-m", "apply configuration variant")
    if damage is None:
        plan = create_plan(root, path)
        assert set(p for lane in plan.partitions for p in lane) == {
            "checks/test_a.py",
            "checks/test_b.py",
        }
    else:
        with pytest.raises(ValueError):
            create_plan(root, path)


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
