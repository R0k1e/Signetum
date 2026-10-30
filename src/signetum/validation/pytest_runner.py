"""Run pytest, retry only failed nodes once serially, and retain first failures."""

from __future__ import annotations

import importlib.util
import json
import os
import resource
import subprocess  # nosec B404 -- fixed Python executable, argv, no shell
import sys
import tempfile
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path


def _schedule_source() -> Path:
    sibling = Path(__file__).with_name("test_scheduling.py")
    return sibling if sibling.is_file() else Path(__file__).parents[1] / "test_scheduling.py"


def _validate_weights(weights):
    spec = importlib.util.spec_from_file_location("_signetum_schedule", _schedule_source())
    if spec is None or spec.loader is None:
        raise ValueError("scheduling implementation unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ordered_units((), weights)


def _options(arguments: list[str], *options: str) -> list[str]:
    separator = arguments.index("--") if "--" in arguments else len(arguments)
    return [*arguments[:separator], *options, *arguments[separator:]]


def _run(
    arguments: list[str], report: Path, *, nodes: list[str] | None = None
) -> tuple[int, list[dict[str, str]]]:
    prepared_at = time.perf_counter()
    environment = dict(os.environ, SIGNETUM_PYTEST_REPORT=str(report))
    environment.pop("SIGNETUM_SCHEDULE_WEIGHTS", None)
    if os.environ.get("SIGNETUM_JOB_SCRATCH"):
        environment["SIGNETUM_PYTEST_SCRATCH"] = str(report.parent / f"temporary-{report.stem}")
    else:
        environment.pop("SIGNETUM_PYTEST_SCRATCH", None)
    # Pytest controllers and xdist workers load the same packaged plugin without
    # importing the engine. Only this temporary directory joins their search path.
    plugins = report.parent / "plugins"
    plugins.mkdir(exist_ok=True)
    (plugins / "_signetum_pytest_report.py").write_bytes(
        Path(__file__).with_name("pytest_report.py").read_bytes()
    )
    scheduling = _schedule_source()
    (plugins / "_signetum_test_scheduling.py").write_bytes(scheduling.read_bytes())
    if weight_path := environment.get("SIGNETUM_SCHEDULE_FILE"):
        weights = json.loads(Path(weight_path).read_text())
        _validate_weights(weights)
        environment["SIGNETUM_SCHEDULE_WEIGHTS"] = json.dumps(weights)
        declared_dist = [
            arg.split("=", 1)[1] if arg.startswith("--dist=") else arguments[n + 1]
            for n, arg in enumerate(arguments)
            if arg.startswith("--dist=") or (arg == "--dist" and n + 1 < len(arguments))
        ]
        if any(value != "loadgroup" for value in declared_dist):
            raise ValueError("weighted scheduling requires loadgroup; correct the declared runner")
        if importlib.util.find_spec("xdist") is not None and not declared_dist:
            arguments = _options(arguments, "--dist=loadgroup")
    search = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(plugins) + (os.pathsep + search if search else "")
    environment.pop("SIGNETUM_RETRY_NODES", None)
    # A fresh controller, including serial retries, must not inherit an outer
    # xdist worker identity. Its own workers receive new identities from xdist.
    for name in tuple(environment):
        if name.startswith("PYTEST_XDIST_"):
            environment.pop(name)
    if (workers := environment.get("SIGNETUM_VALIDATION_WORKERS")) is not None:
        if not workers.isdecimal():
            raise ValueError("invalid allocated worker count")
        if importlib.util.find_spec("xdist") is not None:
            arguments = _options(arguments, "-n", workers)
        elif int(workers):
            raise RuntimeError("allocated workers require pytest-xdist")
    if nodes is not None:
        environment["SIGNETUM_RETRY_NODES"] = json.dumps(nodes)
        arguments = _options(arguments, "-k", "", "-m", "", "--maxfail=0")
        if importlib.util.find_spec("xdist") is not None:
            arguments = _options(arguments, "-n0")
        if importlib.util.find_spec("pytest_cov") is not None:
            arguments = _options(arguments, "--cov-append")
    if not any(arg.startswith("--durations") for arg in arguments):
        arguments = _options(arguments, "--durations=20")
    started = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = subprocess.run(  # noqa: S603  # nosec B603 -- fixed executable, no shell
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0,sys.argv.pop(1)); import pytest; "
            "raise SystemExit(pytest.main(sys.argv[1:]))",
            str(plugins),
            "-p",
            "_signetum_pytest_report",
            *arguments,
        ],
        env=environment,
        check=False,
    )
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cost = {
        "event": "validation.pytest",
        "attempt": "retry" if nodes is not None else "first",
        "exit_code": result.returncode,
        "wall_seconds": time.perf_counter() - started,
        "runner_preparation_seconds": started - prepared_at,
        "child_cpu_seconds": (after.ru_utime + after.ru_stime)
        - (before.ru_utime + before.ru_stime),
        "largest_child_peak_rss_kib": after.ru_maxrss / (1024 if sys.platform == "darwin" else 1),
        "workers": 0
        if nodes is not None
        else int(environment.get("SIGNETUM_VALIDATION_WORKERS", "0")),
    }
    if not report.exists():
        print(json.dumps(cost), file=sys.stderr)
        return result.returncode, []
    document = json.loads(report.read_text(encoding="utf-8"))
    cost.update(
        {
            key: document.get(key)
            for key in (
                "phase_seconds",
                "collection_seconds",
                "worker_collection_seconds",
                "preparation_seconds",
                "execution_seconds",
            )
        }
    )
    cost["workers"] = document.get("workers", cost["workers"])
    print(json.dumps(cost), file=sys.stderr)
    if document["exit_code"] != result.returncode:
        return result.returncode, []
    return result.returncode, document["reports"]


@contextmanager
def _observed_scratch(context, deferred):
    cleanup_started = None
    try:
        with context as scratch:
            try:
                yield scratch
            finally:
                cleanup_started = time.perf_counter()
    finally:
        if cleanup_started is not None:
            print(
                json.dumps(
                    {
                        "event": "validation.pytest.cleanup",
                        "elapsed_seconds": time.perf_counter() - cleanup_started,
                        "deferred_to_supervisor": deferred,
                    }
                ),
                file=sys.stderr,
            )


def main(arguments: list[str] | None = None) -> int:
    supplied = sys.argv[1:] if arguments is None else arguments
    if supplied[:1] == ["--"]:
        supplied = supplied[1:]
    # An enclosing command owns the final cleanup. Removing these paths here
    # would discard the cwd ownership channel before its process inventory.
    parent = os.environ.get("SIGNETUM_JOB_SCRATCH")
    context = (
        nullcontext(tempfile.mkdtemp(prefix="signetum-pytest-", dir=parent))
        if parent
        else tempfile.TemporaryDirectory(prefix="signetum-pytest-")
    )
    with _observed_scratch(context, bool(parent)) as scratch:
        root = Path(scratch)
        status, reports = _run(supplied, root / "first.json")
        if status != 1:
            return status
        failed = sorted({report["node_id"] for report in reports if report["outcome"] == "failed"})
        if not failed or len(failed) > 30:
            return status
        _, retried = _run(supplied, root / "retry.json", nodes=failed)
        recovered = []
        for node in failed:
            outcomes = [report for report in retried if report["node_id"] == node]
            if not any(report["outcome"] == "failed" for report in outcomes) and any(
                report["phase"] == "call" and report["outcome"] == "passed" for report in outcomes
            ):
                recovered.append(
                    {
                        "node_id": node,
                        "first_failure": [
                            report for report in reports if report["node_id"] == node
                        ],
                    }
                )
        if destination := os.environ.get("SIGNETUM_RECOVERY_REPORT"):
            Path(destination).write_text(json.dumps(recovered), encoding="utf-8")
        for defect in recovered:
            print(f"diagnostic retry passed for failed node: {defect['node_id']}", file=sys.stderr)
        # Retrying a narrower, serial workload is diagnostic evidence. Only a
        # fresh normal execution may prove the source after the defect is fixed.
        return status


if __name__ == "__main__":
    raise SystemExit(main())
