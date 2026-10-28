# Generated from signetum.validation.pytest_report; edit the engine source and regenerate.
"""Pytest subprocess plugin; node/phase evidence, including xdist reports."""

import json
import os
from pathlib import Path

_reports: list[dict[str, str]] = []


def _node_id(value: str) -> str:
    # xdist group suffixes follow the test/parameter ID. Preserve '@' in parameters.
    marker = value.rfind("@")
    return value[:marker] if marker > max(value.rfind("]"), value.rfind("::")) else value


def pytest_collection_modifyitems(items):
    if nodes := os.environ.get("SIGNETUM_RETRY_NODES"):
        selected = set(json.loads(nodes))
        items[:] = [item for item in items if _node_id(item.nodeid) in selected]


def pytest_runtest_logreport(report):
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
            json.dumps({"exit_code": int(exitstatus), "reports": _reports}), encoding="utf-8"
        )
