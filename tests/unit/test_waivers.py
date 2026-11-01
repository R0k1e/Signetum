"""Waivers are tracked, approved, expiring coverage rather than a bypass."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from signetum.findings import Finding
from signetum.waivers import Waiver, WaiverError, cover_findings, load_waivers, parse_waiver

WAIVER = """[waiver]
schema_version = 1
id = "audit-demo"
shard = "engine:audit"
findings = ["GHSA-aaaa-bbbb-cccc"]
reason = "Upstream fix pending"
approved_by = "maintainer"
expires = 2026-12-31
"""


def _write(repository: Path, relative: str, body: str) -> Path:
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _finding(identifier: str = "GHSA-aaaa-bbbb-cccc") -> Finding:
    return Finding(identifier, "pip:demo@1.0", "Demo")


def _waiver(**overrides: object) -> Waiver:
    values: dict[str, object] = {
        "schema_version": 1,
        "id": "audit-demo",
        "shard": "engine:audit",
        "findings": ("GHSA-aaaa-bbbb-cccc",),
        "reason": "Upstream fix pending",
        "approved_by": "maintainer",
        "expires": date(2026, 12, 31),
    }
    values.update(overrides)
    return parse_waiver(values)


def test_tracked_waivers_load_from_every_active_change(tmp_path: Path) -> None:
    _write(tmp_path, "changes/one/waivers/audit.toml", WAIVER)
    _write(
        tmp_path,
        "changes/two/waivers/audit.toml",
        WAIVER.replace('id = "audit-demo"', 'id = "audit-other"').replace(
            "2026-12-31", '"2027-01-31"'
        ),
    )

    waivers = load_waivers(tmp_path)

    assert {waiver.id for waiver in waivers} == {"audit-demo", "audit-other"}
    assert {waiver.expires for waiver in waivers} == {date(2026, 12, 31), date(2027, 1, 31)}


def test_a_repository_without_waivers_loads_none(tmp_path: Path) -> None:
    assert load_waivers(tmp_path) == ()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param("not toml = ", "waivers/audit.toml", id="unparsable"),
        pytest.param("[other]\nx = 1\n", "exactly one .waiver. table", id="wrong-table"),
        pytest.param(
            WAIVER.replace("schema_version = 1", "schema_version = 2"),
            "unsupported waiver schema",
            id="wrong-version",
        ),
        pytest.param(
            WAIVER.replace("findings = [", "findings = [] # ["),
            "at least 1 item",
            id="no-findings",
        ),
        pytest.param(
            WAIVER.replace('id = "audit-demo"', 'id = "Audit Demo"'),
            "lowercase and namespaced",
            id="bad-identifier",
        ),
        pytest.param(
            WAIVER.replace('findings = ["GHSA-aaaa-bbbb-cccc"]', 'findings = ["not an id"]'),
            "must be an identifier",
            id="bad-finding",
        ),
        pytest.param(
            WAIVER.replace("expires = 2026-12-31", ""),
            "expires",
            id="missing-expiry",
        ),
        pytest.param(WAIVER + 'extra = "unreviewed"\n', "unsupported", id="unknown-field"),
        pytest.param(
            WAIVER.replace('approved_by = "maintainer"', 'approved_by = ""'),
            "approved_by",
            id="missing-approval",
        ),
        pytest.param(
            WAIVER.replace("schema_version = 1", "schema_version = true"),
            "schema",
            id="boolean-version",
        ),
    ],
)
def test_a_malformed_waiver_fails_closed(tmp_path: Path, body: str, expected: str) -> None:
    _write(tmp_path, "changes/one/waivers/audit.toml", body)

    with pytest.raises(WaiverError, match=expected):
        load_waivers(tmp_path)


def test_duplicate_waiver_identities_are_refused(tmp_path: Path) -> None:
    _write(tmp_path, "changes/one/waivers/audit.toml", WAIVER)
    _write(tmp_path, "changes/two/waivers/audit.toml", WAIVER)

    with pytest.raises(WaiverError, match="duplicate waiver identities: audit-demo"):
        load_waivers(tmp_path)


def test_duplicate_findings_inside_one_waiver_are_refused(tmp_path: Path) -> None:
    body = WAIVER.replace(
        'findings = ["GHSA-aaaa-bbbb-cccc"]',
        'findings = ["GHSA-aaaa-bbbb-cccc", "GHSA-aaaa-bbbb-cccc"]',
    )
    _write(tmp_path, "changes/one/waivers/audit.toml", body)

    with pytest.raises(WaiverError, match="must be unique"):
        load_waivers(tmp_path)


def test_live_authority_covers_exactly_the_findings_it_names() -> None:
    outcome = cover_findings("engine:audit", (_finding(),), (_waiver(),), today=date(2026, 9, 2))

    assert outcome.covered is True
    assert outcome.waivers == ("audit-demo",)
    assert outcome.uncovered == ()


def test_an_expired_waiver_is_reported_rather_than_silently_ignored() -> None:
    outcome = cover_findings(
        "engine:audit",
        (_finding(),),
        (_waiver(expires=date(2026, 9, 1)),),
        today=date(2026, 9, 2),
    )

    assert outcome.covered is False
    assert outcome.uncovered == ("GHSA-aaaa-bbbb-cccc",)
    assert outcome.expired == ("audit-demo",)
    assert "expired waivers: audit-demo" in outcome.diagnostic("engine:audit")


def test_a_failure_reporting_nothing_is_never_covered() -> None:
    outcome = cover_findings("engine:audit", (), (_waiver(),), today=date(2026, 9, 2))

    assert outcome.covered is False
    assert outcome.diagnostic("engine:audit") == (
        "world shard engine:audit reported unwaived findings"
    )


def test_a_waiver_expiring_today_still_carries_authority() -> None:
    assert _waiver(expires=date(2026, 9, 2)).usable(today=date(2026, 9, 2)) is True
    assert _waiver(expires=date(2026, 9, 1)).usable(today=date(2026, 9, 2)) is False


@pytest.mark.parametrize(
    ("body", "day", "expected"),
    [
        (WAIVER, "2026-12-31", "waived"),
        (WAIVER, "2027-01-01", "expired"),
        (WAIVER + 'extra = "unreviewed"\n', "2026-12-31", "refused"),
        (WAIVER.replace('approved_by = "maintainer"', 'approved_by = ""'), "2026-12-31", "refused"),
        (
            WAIVER.replace('reason = "Upstream fix pending"', 'reason = "   "'),
            "2026-12-31",
            "refused",
        ),
        (WAIVER.replace("schema_version = 1", "schema_version = true"), "2026-12-31", "refused"),
        (WAIVER.replace("expires = 2026-12-31", 'expires = "yesterday"'), "2026-12-31", "refused"),
    ],
)
def test_engine_and_independent_template_use_the_same_waiver_authority(
    tmp_path: Path, body: str, day: str, expected: str
) -> None:
    root = Path(__file__).parents[2]
    _write(tmp_path, "changes/one/waivers/audit.toml", body)
    script = """
import importlib, json, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, sys.argv[1])
module = importlib.import_module(sys.argv[2])
load = module.load_waivers
cover = module.cover_findings
Finding = importlib.import_module(sys.argv[2].rsplit('.', 1)[0] + '.findings').Finding
try:
    waivers = load(Path(sys.argv[3]))
    outcome = cover('engine:audit', (Finding('GHSA-aaaa-bbbb-cccc', 'demo', 'Demo'),),
                    waivers, today=date.fromisoformat(sys.argv[4]))
    result = {'status': 'waived' if outcome.covered else 'expired',
              'waivers': outcome.waivers, 'expired': outcome.expired,
              'uncovered': outcome.uncovered}
except ValueError as error:
    result = {'status': 'refused', 'reason': str(error)}
assert 'pydantic' not in sys.modules
print(json.dumps(result))
"""
    completed = subprocess.run(  # noqa: S603 -- source-only pure waiver rules
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            script,
            str(root / "skills/signetum/scripts/engine"),
            "signetum.waivers",
            str(tmp_path),
            day,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == expected
