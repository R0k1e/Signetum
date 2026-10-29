"""Pytest subprocess plugin; node/phase evidence, including xdist reports."""

import json
import os
from pathlib import Path

_reports: list[dict[str, str]] = []
_phase_seconds: dict[str, float] = {}


def _node_id(value: str) -> str:
    # xdist group suffixes follow the test/parameter ID. Preserve '@' in parameters.
    marker = value.rfind("@")
    return value[:marker] if marker > max(value.rfind("]"), value.rfind("::")) else value


def pytest_configure(config):
    # Respect both CLI and repository-configured basetemp. Workers receive the
    # controller's explicit per-worker path and must not replace it.
    if config.option.basetemp is None and (scratch := os.environ.get("SIGNETUM_PYTEST_SCRATCH")):
        config.option.basetemp = scratch


def pytest_collection_modifyitems(items):
    if nodes := os.environ.get("SIGNETUM_RETRY_NODES"):
        selected = set(json.loads(nodes))
        items[:] = [item for item in items if _node_id(item.nodeid) in selected]


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


def pytest_sessionfinish(session, exitstatus):
    # Workers report through the controller. Only that controller owns the file.
    if not hasattr(session.config, "workerinput"):
        Path(os.environ["SIGNETUM_PYTEST_REPORT"]).write_text(
            json.dumps(
                {
                    "exit_code": int(exitstatus),
                    "reports": _reports,
                    "phase_seconds": _phase_seconds,
                    "workers": session.config.getoption("numprocesses", default=0) or 0,
                }
            ),
            encoding="utf-8",
        )
