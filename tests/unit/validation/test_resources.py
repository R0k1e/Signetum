"""Declared concurrency cannot exceed observed CPU or memory capacity."""

import json
import sys
from dataclasses import replace

import pytest

from signetum.manifest import ValidationShard as ManifestShard
from signetum.validation import (
    GraphContribution,
    ValidationConfiguration,
    ValidationGraphError,
    ValidationShard,
    resolve_validation_graph,
)
from signetum.validation.execution import ValidationInfrastructureError
from signetum.validation.repository import RepositoryValidationAdapter
from signetum.validation.resources import ResourceObservation, allocate_workers, observe_resources


@pytest.mark.parametrize(
    ("cpus", "memory", "expected"), [(2, 10000, 2), (20, 2500, 2), (20, 20000, 8)]
)
def test_worker_ceiling_respects_both_observed_bounds(cpus, memory, expected):
    allocation = allocate_workers(8, 1000, ResourceObservation(cpus, memory))
    assert allocation["workers"] == expected
    assert allocation["declared_workers"] == 8
    assert allocation["available_memory_mb"] == memory


def test_no_affordable_worker_refuses_instead_of_overcommitting():
    with pytest.raises(ValidationInfrastructureError, match="memory"):
        allocate_workers(8, 1000, ResourceObservation(8, 999))


def test_cgroup_ancestors_bound_cpu_and_available_memory(tmp_path):
    child = tmp_path / "group" / "child"
    child.mkdir(parents=True)
    (tmp_path / "cpu.max").write_text("250000 100000")
    (child / "cpu.max").write_text("max 100000")
    (tmp_path / "memory.max").write_text(str(4000 * 1024 * 1024))
    (tmp_path / "memory.current").write_text(str(2500 * 1024 * 1024))
    observation = observe_resources(cgroup_root=tmp_path, cgroup_path=child)
    assert observation.cpus <= 2
    assert observation.available_memory_mb <= 1500


def test_invalid_cgroup_measurement_is_infrastructure_failure(tmp_path):
    (tmp_path / "cpu.max").write_text("corrupt")
    with pytest.raises(ValidationInfrastructureError, match="resource"):
        observe_resources(cgroup_root=tmp_path, cgroup_path=tmp_path)


def test_repository_passes_recorded_allocation_to_actual_command(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "signetum.validation.resources.observe_resources", lambda: ResourceObservation(2, 3000)
    )
    script = (
        "import os; from pathlib import Path; "
        "Path('observed.json').write_text(os.environ['SIGNETUM_VALIDATION_WORKERS'])"
    )
    result = RepositoryValidationAdapter(tmp_path).run_shard(
        ValidationShard(
            "test:bounded", (sys.executable, "-c", script), workers=8, worker_memory_mb=1000
        )
    )
    assert result.succeeded
    assert json.loads((tmp_path / "observed.json").read_text()) == 2
    allocation = result.details["resource_allocation"]
    assert isinstance(allocation, dict)
    assert allocation["workers"] == 2


def test_actual_pytest_workers_consume_allocation_and_retry_serially(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "outer-worker")
    monkeypatch.setenv("PYTEST_XDIST_WORKER_COUNT", "64")
    monkeypatch.setattr(
        "signetum.validation.resources.observe_resources", lambda: ResourceObservation(2, 3000)
    )
    (tmp_path / "test_bounded.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "def test_bounded():\n"
        "    marker=Path(__file__).with_suffix('.first')\n"
        "    if not marker.exists():\n"
        "        assert os.environ['PYTEST_XDIST_WORKER_COUNT']=='2'\n"
        "        marker.touch()\n"
        "        assert False, 'retry serially'\n"
        "    assert 'PYTEST_XDIST_WORKER' not in os.environ\n"
    )
    result = RepositoryValidationAdapter(tmp_path).run_shard(
        ValidationShard(
            "test:pytest",
            (
                sys.executable,
                "-m",
                "signetum.validation.pytest_runner",
                "--",
                "-q",
                "-o",
                "addopts=",
                "test_bounded.py",
            ),
            workers=8,
            worker_memory_mb=1000,
        )
    )
    assert result.succeeded, result.diagnostic
    assert len(result.recovered) == 1
    assert "retry serially" in str(result.recovered)


@pytest.mark.parametrize("field", ["workers", "worker_memory_mb"])
@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_invalid_worker_budget_cannot_enter_graph(field, value):
    with pytest.raises(ValidationGraphError, match="worker budgets"):
        ValidationShard("test:invalid", ("true",), **{field: value})


def test_worker_configuration_changes_graph_identity():
    shard = ValidationShard("test:bounded", ("true",), workers=8, worker_memory_mb=1000)

    def digest(value):
        return resolve_validation_graph((GraphContribution("test", (value,)),)).digest

    assert digest(shard) != digest(replace(shard, workers=4))
    assert digest(shard) != digest(replace(shard, worker_memory_mb=2000))


def test_legacy_cgroup_quotas_are_applied(tmp_path):
    (tmp_path / "cpu.cfs_quota_us").write_text("100000")
    (tmp_path / "cpu.cfs_period_us").write_text("100000")
    (tmp_path / "memory.limit_in_bytes").write_text(str(2000 * 1024 * 1024))
    (tmp_path / "memory.usage_in_bytes").write_text(str(1000 * 1024 * 1024))
    value = observe_resources(cgroup_root=tmp_path, cgroup_path=tmp_path)
    assert value.cpus == 1
    assert value.available_memory_mb <= 1000


@pytest.mark.parametrize("legacy", [False, True])
def test_membership_resolves_declared_container_limits(tmp_path, legacy):
    root = tmp_path / "cgroups"
    group = root / "cpu,memory" / "leaf" if legacy else root / "leaf"
    group.mkdir(parents=True)
    (group / "cpu.max").write_text("100000 100000")
    (group / "memory.max").write_text("max")
    membership = tmp_path / "membership"
    membership.write_text("2:cpu,memory:/leaf\n" if legacy else "0::/leaf\n")
    observation = observe_resources(cgroup_root=root, membership_file=membership)
    assert observation.cpus == 1


def test_membership_outside_resource_mount_is_refused(tmp_path):
    with pytest.raises(ValidationInfrastructureError, match="resource root"):
        observe_resources(cgroup_root=tmp_path / "mount", cgroup_path=tmp_path)


def test_profile_and_repository_budget_projections_agree():
    raw = {"name": "test:budget", "command": ["true"], "workers": 4, "worker_memory_mb": 512}
    profile = ValidationConfiguration.from_mapping("test", {"shards": [raw]}).contribution.shards[0]
    repository = ManifestShard.model_validate(raw)
    assert profile.workers == repository.workers == 4
    assert profile.worker_memory_mb == repository.worker_memory_mb == 512
