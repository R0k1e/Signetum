"""The Python profile owns the translation from pip-audit into findings."""

import json
import subprocess

import pytest

from signetum.findings import FindingsError, parse_findings
from signetum.profiles import pip_audit

REPORT = json.dumps(
    {
        "dependencies": [
            {
                "name": "demo",
                "version": "1.0",
                "vulns": [
                    {"id": "GHSA-aaaa-bbbb-cccc", "description": "Leaks headers\nand more"},
                    {"id": "GHSA-aaaa-bbbb-cccc"},
                ],
            },
            {"name": "clean", "version": "2.0", "vulns": []},
            {"name": "unversioned", "vulns": [{"id": "CVE-2026-0001"}]},
            "not a mapping",
        ]
    }
)


def test_a_report_translates_into_the_neutral_findings_document() -> None:
    findings = parse_findings(pip_audit.translate(REPORT))

    assert [finding.id for finding in findings] == ["CVE-2026-0001", "GHSA-aaaa-bbbb-cccc"]
    assert findings[1].locator == "pip:demo@1.0"
    assert findings[1].summary == "Leaks headers"
    assert findings[0].locator == "pip:unversioned"
    assert findings[0].summary == "unversioned  is affected by CVE-2026-0001"


def test_a_clean_report_translates_into_an_empty_document() -> None:
    assert parse_findings(pip_audit.translate('{"dependencies": []}')) == ()


def test_a_bare_dependency_array_is_also_accepted() -> None:
    document = '[{"name": "demo", "version": "1.0", "vulns": [{"id": "CVE-2026-0002"}]}]'

    assert parse_findings(pip_audit.translate(document))[0].id == "CVE-2026-0002"


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        pytest.param("not json", "did not emit JSON", id="not-json"),
        pytest.param('{"other": 1}', "no dependency array", id="no-dependencies"),
    ],
)
def test_an_untranslatable_report_fails_closed(document: str, expected: str) -> None:
    with pytest.raises(FindingsError, match=expected):
        pip_audit.translate(document)


def test_report_runs_the_tool_and_ignores_its_finding_exit_status(monkeypatch) -> None:
    monkeypatch.setattr(pip_audit, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        pip_audit.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, REPORT, ""),
    )

    assert parse_findings(pip_audit.report())[1].id == "GHSA-aaaa-bbbb-cccc"


def test_report_fails_when_the_tool_is_absent(monkeypatch) -> None:
    monkeypatch.setattr(pip_audit, "which", lambda name: None)

    with pytest.raises(FindingsError, match="unavailable"):
        pip_audit.report()


def test_report_fails_when_the_tool_produced_nothing(monkeypatch) -> None:
    monkeypatch.setattr(pip_audit, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        pip_audit.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 2, "", "network unreachable"),
    )

    with pytest.raises(FindingsError, match="network unreachable"):
        pip_audit.report()
