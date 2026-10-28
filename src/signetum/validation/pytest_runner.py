"""Run pytest, retry only failed nodes once serially, and retain first failures."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess  # nosec B404 -- fixed Python executable, argv, no shell
import sys
import tempfile
from pathlib import Path


def _run(
    arguments: list[str], report: Path, *, nodes: list[str] | None = None
) -> tuple[int, list[dict[str, str]]]:
    environment = dict(os.environ, SIGNETUM_PYTEST_REPORT=str(report))
    # Pytest controllers and xdist workers load the same packaged plugin without
    # importing the engine. Only this temporary directory joins their search path.
    plugins = report.parent / "plugins"
    plugins.mkdir(exist_ok=True)
    (plugins / "_signetum_pytest_report.py").write_bytes(
        Path(__file__).with_name("pytest_report.py").read_bytes()
    )
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
            arguments = [*arguments, "-n", workers]
        elif int(workers):
            raise RuntimeError("allocated workers require pytest-xdist")
    if nodes is not None:
        environment["SIGNETUM_RETRY_NODES"] = json.dumps(nodes)
        arguments = [*arguments, "-k", "", "-m", "", "--maxfail=0"]
        if importlib.util.find_spec("xdist") is not None:
            arguments.append("-n0")
        if importlib.util.find_spec("pytest_cov") is not None:
            arguments.append("--cov-append")
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
    if not report.exists():
        return result.returncode, []
    document = json.loads(report.read_text(encoding="utf-8"))
    if document["exit_code"] != result.returncode:
        return result.returncode, []
    return result.returncode, document["reports"]


def main(arguments: list[str] | None = None) -> int:
    supplied = sys.argv[1:] if arguments is None else arguments
    if supplied[:1] == ["--"]:
        supplied = supplied[1:]
    with tempfile.TemporaryDirectory(prefix="signetum-pytest-") as scratch:
        root = Path(scratch)
        status, reports = _run(supplied, root / "first.json")
        if status != 1:
            return status
        failed = sorted({report["node_id"] for report in reports if report["outcome"] == "failed"})
        if not failed or len(failed) > 30:
            return status
        retry_status, retried = _run(supplied, root / "retry.json", nodes=failed)
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
            print(f"recovered robustness defect: {defect['node_id']}", file=sys.stderr)
        return 0 if retry_status == 0 and len(recovered) == len(failed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
