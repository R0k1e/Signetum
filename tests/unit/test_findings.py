"""The findings document is the only contract a world shard reports through."""

import json

import pytest

from signetum.findings import Finding, FindingsError, parse_findings


def _document(*findings: dict[str, str]) -> str:
    return json.dumps({"schema_version": 1, "findings": list(findings)})


def _finding(**overrides: str) -> dict[str, str]:
    values = {"id": "GHSA-aaaa-bbbb-cccc", "locator": "pip:demo@1.0", "summary": "Demo"}
    values.update(overrides)
    return values


def test_a_valid_document_parses_into_sorted_unique_findings() -> None:
    document = _document(
        _finding(id="GHSA-zzzz-yyyy-xxxx"),
        _finding(id="CVE-2026-0001", locator="pip:other@2.0"),
    )

    findings = parse_findings(document)

    assert [finding.id for finding in findings] == ["CVE-2026-0001", "GHSA-zzzz-yyyy-xxxx"]
    assert findings[0].locator == "pip:other@2.0"


def test_an_empty_finding_list_is_a_valid_document() -> None:
    assert parse_findings(_document()) == ()


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        pytest.param("not json", "not JSON", id="not-json"),
        pytest.param("[]", "must be an object", id="not-an-object"),
        pytest.param('{"schema_version":2,"findings":[]}', "unsupported", id="wrong-version"),
        pytest.param('{"schema_version":1,"findings":{}}', "must be an array", id="not-an-array"),
        pytest.param(
            '{"schema_version":1,"findings":["x"]}', "must be an object", id="finding-not-object"
        ),
        pytest.param(
            json.dumps({"schema_version": 1, "findings": [{"id": "GHSA-a"}]}),
            "missing locator, summary",
            id="incomplete-finding",
        ),
        pytest.param(
            json.dumps({"schema_version": 1, "findings": [_finding() | {"severity": "high"}]}),
            "unsupported fields",
            id="extra-fields",
        ),
        pytest.param(
            json.dumps({"schema_version": 1, "findings": [_finding() | {"summary": 3}]}),
            "must be strings",
            id="non-string-field",
        ),
        pytest.param(_document(_finding(), _finding()), "duplicate finding", id="duplicate"),
    ],
)
def test_an_invalid_document_fails_closed(document: str, expected: str) -> None:
    with pytest.raises(FindingsError, match=expected):
        parse_findings(document)


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({"id": "not an id"}, id="identifier-charset"),
        pytest.param({"locator": ""}, id="locator-required"),
        pytest.param({"summary": ""}, id="summary-required"),
    ],
)
def test_finding_values_fail_closed(values: dict[str, str]) -> None:
    with pytest.raises(FindingsError):
        Finding(**_finding(**values))
