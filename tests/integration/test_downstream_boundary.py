from dataclasses import dataclass

from reposeal.evidence import CheckResult, RepositoryAdapter, run_check
from reposeal.manifest import load_manifest


@dataclass(frozen=True)
class FixtureAdapter(RepositoryAdapter):
    observed_architecture: str = ""

    def validate(self, architecture: str) -> CheckResult:
        return CheckResult(check="fixture", passed=architecture == "docs/ARCHITECTURE.md")


def test_repository_facts_reach_only_downstream_adapter() -> None:
    manifest = load_manifest("tests/fixtures/repository.yaml")

    result = run_check(manifest, FixtureAdapter())

    assert result == CheckResult(check="fixture", passed=True)
