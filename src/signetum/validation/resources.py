"""Live host observations and language-neutral worker allocation."""

import os
import re
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path

from signetum.validation.execution import ValidationInfrastructureError
from signetum.validation.process import run_command


@dataclass(frozen=True)
class ResourceObservation:
    cpus: int
    available_memory_mb: int

    def __post_init__(self) -> None:
        if type(self.cpus) is not int or self.cpus < 1:
            raise ValidationInfrastructureError("resource CPU observation must be positive")
        if type(self.available_memory_mb) is not int or self.available_memory_mb < 0:
            raise ValidationInfrastructureError("resource memory observation must be non-negative")


def available_memory_bytes(platform: str, document: str) -> int:
    """Read Linux available memory or Darwin free plus inactive native pages."""

    if platform == "linux":
        values = re.findall(r"^MemAvailable:[ \t]*([0-9]+)[ \t]+kB[ \t]*$", document, re.MULTILINE)
        if len(values) != 1:
            raise ValueError("MemAvailable measurement is unavailable")
        return int(values[0]) * 1024
    if platform == "darwin":
        page = re.search(r"page size of ([1-9][0-9]*) bytes", document)
        values = re.findall(
            r"^Pages (free|inactive):[ \t]*([0-9]+)\.[ \t]*$", document, re.MULTILINE
        )
        if page is None or len(values) != 2 or {name for name, _ in values} != {"free", "inactive"}:
            raise ValueError("Darwin page measurements are unavailable")
        return sum(int(value) for _, value in values) * int(page[1])
    raise ValueError(f"native resource observation is unavailable on {platform}")


def observe_host(
    *, platform: str | None = None, meminfo: Path = Path("/proc/meminfo")
) -> ResourceObservation:
    """Observe a native host without loading distribution-specific dependencies."""

    platform = sys.platform if platform is None else platform
    affinity = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else ()
    cpus = len(affinity) or os.cpu_count()
    if cpus is None:
        raise ValueError("CPU capacity is unavailable")
    if platform == "linux":
        document = meminfo.read_text()
    elif platform == "darwin":
        observed = run_command(Path.cwd(), ("/usr/bin/vm_stat",), timeout_seconds=60)
        if observed.returncode:
            raise ValueError(f"Darwin memory observation failed: {observed.stderr.strip()}")
        document = observed.stdout
    else:
        raise ValueError(f"native resource observation is unavailable on {platform}")
    return ResourceObservation(cpus, available_memory_bytes(platform, document) // (1024 * 1024))


def observe_resources(
    *,
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    cgroup_path: Path | None = None,
    membership_file: Path = Path("/proc/self/cgroup"),
    host: ResourceObservation | None = None,
) -> ResourceObservation:
    """Respect affinity and visible ancestor quotas, including memory headroom."""
    try:
        observed = observe_host() if host is None else host
        cpus = observed.cpus
        available = observed.available_memory_mb * 1024 * 1024
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
    except (OSError, ValueError, ZeroDivisionError, subprocess.TimeoutExpired) as error:
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
