import io
import json
from pathlib import Path

from reposeal.status.models import (
    DeliveryObservation,
    EvidenceSnapshot,
    IntegrationObservation,
    MemberObservation,
)
from reposeal.traceability.boundary import (
    RepositoryInventory,
    TraceabilityManifest,
)
from reposeal.traceability.cli import ExitCode, query

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


class EmptyInventory:
    def read(self, repository: Path) -> RepositoryInventory:
        return RepositoryInventory(paths=frozenset())


class FailingInventory:
    def read(self, repository: Path) -> RepositoryInventory:
        raise OSError("inventory unavailable")


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
        deliveries=(DeliveryObservation(batch_commit="batch", delivery_commit="delivery-1"),),
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


def test_public_query_rejects_a_repository_without_changes() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = query(
        FIXTURE,
        TraceabilityManifest(schema_version=1),
        EvidenceSnapshot(),
        stdout,
        stderr,
        EmptyInventory(),
    )

    assert exit_code is ExitCode.VALIDATION_FAILURE
    assert json.loads(stdout.getvalue())["valid"] is False


def test_public_query_maps_inventory_errors_to_the_invocation_contract() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = query(
        FIXTURE,
        TraceabilityManifest(schema_version=1),
        EvidenceSnapshot(),
        stdout,
        stderr,
        FailingInventory(),
    )

    assert exit_code is ExitCode.INVOCATION_ERROR
    assert json.loads(stdout.getvalue())["issues"][0]["code"] == "invocation-error"
    assert "inventory unavailable" in stderr.getvalue()
