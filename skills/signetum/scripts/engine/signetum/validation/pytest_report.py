"""Pytest subprocess plugin; node/phase evidence, including xdist reports."""

import importlib
import importlib.util
import json
import os
import time
from pathlib import Path

_reports: list[dict[str, str]] = []
_phase_seconds: dict[str, float] = {}
_collection_started = 0.0
_collection_seconds = 0.0
_configured = 0.0
_session_started = 0.0
_execution_started = 0.0
_weights: dict[str, float] = {}
_worker_collection_seconds = 0.0
_pytest = importlib.import_module("pytest")


def _node_id(value: str) -> str:
    # xdist group suffixes follow the test/parameter ID. Preserve '@' in parameters.
    marker = value.rfind("@")
    return value[:marker] if marker > max(value.rfind("]"), value.rfind("::")) else value


def pytest_configure(config):
    global _configured, _weights, _execution_started, _collection_seconds
    global _worker_collection_seconds, _collection_started, _session_started
    _execution_started = _collection_seconds = _worker_collection_seconds = 0.0
    _collection_started = _session_started = 0.0
    _configured = time.perf_counter()
    _reports.clear()
    _phase_seconds.clear()
    _weights = json.loads(os.environ.get("SIGNETUM_SCHEDULE_WEIGHTS", "{}"))
    # Respect both CLI and repository-configured basetemp. Workers receive the
    # controller's explicit per-worker path and must not replace it.
    if config.option.basetemp is None and (scratch := os.environ.get("SIGNETUM_PYTEST_SCRATCH")):
        config.option.basetemp = scratch


def pytest_sessionstart(session):
    global _session_started
    _session_started = time.perf_counter()


def pytest_collection(session):
    global _collection_started
    _collection_started = time.perf_counter()


def pytest_collection_finish(session):
    global _collection_seconds
    _collection_seconds = time.perf_counter() - _collection_started


def pytest_collectreport(report):
    if report.failed:
        _reports.append(
            {
                "node_id": report.nodeid,
                "phase": "collect",
                "outcome": "failed",
                "diagnostic": str(report.longrepr),
            }
        )
        _pytest.exit("collection failed; repair before running tests", returncode=2)


def pytest_runtest_logstart(nodeid, location):
    global _execution_started
    if not _execution_started:
        _execution_started = time.perf_counter()


def pytest_collection_modifyitems(items):
    if nodes := os.environ.get("SIGNETUM_RETRY_NODES"):
        selected = set(json.loads(nodes))
        items[:] = [item for item in items if _node_id(item.nodeid) in selected]
    if _weights:
        units = []
        originals = tuple(items)
        for index, item in enumerate(originals):
            groups = sorted(
                {
                    str(mark.args[0] if mark.args else mark.kwargs.get("name", "default"))
                    for mark in item.iter_markers("xdist_group")
                }
            )
            unit = "_".join(groups) if groups else _node_id(item.nodeid)
            units.append((unit, str(index)))
        spec = importlib.util.spec_from_file_location(
            "_signetum_schedule", Path(__file__).with_name("_signetum_test_scheduling.py")
        )
        if spec is None or spec.loader is None:
            raise ValueError("scheduling implementation unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        items[:] = [originals[int(index)] for index in module.ordered_units(units, _weights)]


def pytest_runtest_logreport(report):
    _phase_seconds[report.when] = _phase_seconds.get(report.when, 0.0) + report.duration
    _reports.append(
        {
            "node_id": _node_id(report.nodeid),
            "phase": report.when,
            "outcome": report.outcome,
            "diagnostic": str(report.longrepr) if report.failed else "",
        }
    )


@_pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    global _worker_collection_seconds
    _worker_collection_seconds += node.workeroutput.get("signetum_collection_seconds", 0.0)


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        session.config.workeroutput["signetum_collection_seconds"] = _collection_seconds
    # Workers report through the controller. Only that controller owns the file.
    if not hasattr(session.config, "workerinput"):
        Path(os.environ["SIGNETUM_PYTEST_REPORT"]).write_text(
            json.dumps(
                {
                    "exit_code": int(exitstatus),
                    "reports": _reports,
                    "phase_seconds": _phase_seconds,
                    "workers": session.config.getoption("numprocesses", default=0) or 0,
                    "collection_seconds": _collection_seconds,
                    "worker_collection_seconds": _worker_collection_seconds,
                    "preparation_seconds": max(0.0, _session_started - _configured),
                    "execution_seconds": (
                        max(0.0, time.perf_counter() - _execution_started)
                        if _execution_started
                        else 0.0
                    ),
                }
            ),
            encoding="utf-8",
        )
