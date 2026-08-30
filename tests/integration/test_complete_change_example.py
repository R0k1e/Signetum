import io
import json
from pathlib import Path

from reposeal.status.models import EvidenceSnapshot
from reposeal.traceability.boundary import (
    RepositoryInventory,
    TraceabilityManifest,
)
from reposeal.traceability.cli import ExitCode, query

ROOT = Path(__file__).parents[2] / "template"


class ExampleInventory:
    def read(self, repository: Path) -> RepositoryInventory:
        return RepositoryInventory(
            paths=frozenset(
                path.relative_to(repository).as_posix()
                for path in repository.rglob("*")
                if path.is_file()
            )
        )


def test_complete_change_example_closes_recorded_coverage() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = query(
        ROOT,
        TraceabilityManifest(schema_version=1, changes_root="examples"),
        EvidenceSnapshot(),
        stdout,
        stderr,
        ExampleInventory(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code is ExitCode.SUCCESS
    assert payload["valid"] is True
    assert payload["changes"][0]["clauses"][0]["clause"] == "EXAMPLE-001"
    assert stderr.getvalue() == ""
