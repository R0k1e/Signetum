"""Live host observations and language-neutral worker allocation."""

import os
from dataclasses import dataclass
from pathlib import Path

import psutil

from signetum.validation.execution import ValidationInfrastructureError


@dataclass(frozen=True)
class ResourceObservation:
    cpus: int
    available_memory_mb: int


def observe_resources(
    *,
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    cgroup_path: Path | None = None,
    membership_file: Path = Path("/proc/self/cgroup"),
) -> ResourceObservation:
    """Respect affinity and visible ancestor quotas, including memory headroom."""
    try:
        process = psutil.Process()
        affinity = process.cpu_affinity() if hasattr(process, "cpu_affinity") else ()
        cpus = len(affinity) or os.cpu_count() or 1
        available = psutil.virtual_memory().available
        paths: list[Path] = []
        if cgroup_path is not None:
            paths.append(cgroup_path)
        elif membership_file.is_file():
            for line in membership_file.read_text().splitlines():
                _, controllers, relative = line.split(":", 2)
                if not controllers:
                    paths.append(cgroup_root / relative.lstrip("/"))
                elif "cpu" in controllers.split(",") or "memory" in controllers.split(","):
                    paths.append(cgroup_root / controllers / relative.lstrip("/"))
        for path in paths:
            path = path.resolve()
            root = cgroup_root.resolve()
            if not path.is_relative_to(root):
                raise ValueError("cgroup membership escapes its resource root")
            for directory in (path, *path.parents):
                if not directory.is_relative_to(root):
                    break
                if (quota_file := directory / "cpu.max").is_file():
                    quota, period = quota_file.read_text().split()
                    if quota != "max":
                        cpus = min(cpus, max(1, int(quota) // int(period)))
                elif (quota_file := directory / "cpu.cfs_quota_us").is_file():
                    quota = int(quota_file.read_text())
                    period = int((directory / "cpu.cfs_period_us").read_text())
                    if quota > 0:
                        cpus = min(cpus, max(1, quota // period))
                for limit_name, used_name in (
                    ("memory.max", "memory.current"),
                    ("memory.limit_in_bytes", "memory.usage_in_bytes"),
                ):
                    if (limit_file := directory / limit_name).is_file():
                        limit = limit_file.read_text().strip()
                        if limit != "max":
                            used = int((directory / used_name).read_text())
                            available = min(available, max(0, int(limit) - used))
        return ResourceObservation(cpus, available // (1024 * 1024))
    except (OSError, ValueError, ZeroDivisionError, psutil.Error) as error:
        raise ValidationInfrastructureError(f"resource observation unavailable: {error}") from error


def allocate_workers(
    declared: int, worker_memory_mb: int, observation: ResourceObservation
) -> dict[str, int]:
    """Never launch more workers than either declared or observed capacity."""
    affordable = (
        observation.available_memory_mb // worker_memory_mb if worker_memory_mb else declared
    )
    if declared and affordable < 1:
        raise ValidationInfrastructureError("available memory cannot afford one declared worker")
    count = min(declared, observation.cpus, affordable)
    return {
        "workers": count,
        "declared_workers": declared,
        "effective_cpus": observation.cpus,
        "available_memory_mb": observation.available_memory_mb,
        "worker_memory_mb": worker_memory_mb,
    }
