import io
import json
from pathlib import Path

from development_foundation.status.models import (
    DeliveryObservation,
    EvidenceSnapshot,
    IntegrationObservation,
    MemberObservation,
)
from development_foundation.traceability.boundary import (
    RepositoryInventory,
    TraceabilityManifest,
)
from development_foundation.traceability.cli import ExitCode, query

FIXTURE = Path("tests/fixtures/changes/valid")


class FixtureInventory:
    def read(self, repository: Path) -> RepositoryInventory:
        return RepositoryInventory(
            paths=frozenset(
                path.relative_to(repository).as_posix()
                for path in repository.rglob("*")
                if path.is_file()
            )
        )


def test_public_query_emits_one_versioned_json_object() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    evidence = EvidenceSnapshot(
        members=(
            MemberObservation(plan_id="example/first", commit="m1", ready=True),
            MemberObservation(plan_id="example/second", commit="m2", ready=True),
        ),
        integrations=(
            IntegrationObservation(member_commit="m1", batch_commit="batch"),
            IntegrationObservation(member_commit="m2", batch_commit="batch"),
        ),
        deliveries=(
            DeliveryObservation(batch_commit="batch", delivery_commit="delivery-1"),
        ),
    )
    exit_code = query(
        FIXTURE,
        TraceabilityManifest(schema_version=1),
        evidence,
        stdout,
        stderr,
        FixtureInventory(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code is ExitCode.SUCCESS
    assert stdout.getvalue().count("\n") == 1
    assert payload["schema_version"] == 1
    assert payload["changes"][0]["state"] == "accepted"
    assert stderr.getvalue() == ""
