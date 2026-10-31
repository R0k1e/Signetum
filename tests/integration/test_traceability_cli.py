import io
import json
from pathlib import Path

import pytest
from change_fixtures import consolidated_approval
from signetum.status.models import (
    DeliveryObservation,
    EvidenceSnapshot,
    IntegrationObservation,
    MemberObservation,
)
from signetum.traceability.boundary import (
    RepositoryInventory,
    TraceabilityManifest,
)
from signetum.traceability.cli import ExitCode, query


@pytest.fixture
def record_repository(tmp_path):
    consolidated_approval(tmp_path, "a" * 40)
    return tmp_path


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


def test_historical_yaml_changes_are_read_only_provenance(record_repository) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    inventory = FixtureInventory().read(record_repository)
    historical = RepositoryInventory(
        paths=inventory.paths | {"changes/historical/review.yaml", "changes/historical/review.toml"}
    )

    class InventoryWithHistoricalYaml:
        def read(self, repository: Path) -> RepositoryInventory:
            return historical

    exit_code = query(
        record_repository,
        TraceabilityManifest(schema_version=1, decision_roots=("decisions",)),
        EvidenceSnapshot(),
        stdout,
        stderr,
        InventoryWithHistoricalYaml(),
    )

    assert exit_code is ExitCode.SUCCESS
    assert json.loads(stdout.getvalue())["changes"][0]["review"] == "example"


def test_public_query_emits_one_versioned_json_object(record_repository) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    evidence = EvidenceSnapshot(
        members=(
            MemberObservation(plan_id="changes/example/change.toml", commit="m1", ready=True),
        ),
        integrations=(IntegrationObservation(member_commit="m1", batch_commit="batch"),),
        deliveries=(DeliveryObservation(batch_commit="batch", delivery_commit="delivery-1"),),
    )
    exit_code = query(
        record_repository,
        TraceabilityManifest(schema_version=1, decision_roots=("decisions",)),
        evidence,
        stdout,
        stderr,
        FixtureInventory(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code is ExitCode.SUCCESS
    assert stdout.getvalue().count("\n") == 1
    assert payload["schema_version"] == 1
    assert payload["changes"][0]["state"] == "delivered"
    assert stderr.getvalue() == ""


def test_public_query_rejects_a_repository_without_changes(record_repository) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = query(
        record_repository,
        TraceabilityManifest(schema_version=1, decision_roots=("decisions",)),
        EvidenceSnapshot(),
        stdout,
        stderr,
        EmptyInventory(),
    )

    assert exit_code is ExitCode.VALIDATION_FAILURE
    assert json.loads(stdout.getvalue())["valid"] is False


def test_public_query_maps_inventory_errors_to_the_invocation_contract(record_repository) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = query(
        record_repository,
        TraceabilityManifest(schema_version=1, decision_roots=("decisions",)),
        EvidenceSnapshot(),
        stdout,
        stderr,
        FailingInventory(),
    )

    assert exit_code is ExitCode.INVOCATION_ERROR
    assert json.loads(stdout.getvalue())["issues"][0]["code"] == "invocation-error"
    assert "inventory unavailable" in stderr.getvalue()
