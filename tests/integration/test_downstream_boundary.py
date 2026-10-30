from dataclasses import dataclass

from signetum.evidence import CheckResult, RepositoryAdapter, run_check
from signetum.manifest import load_manifest


@dataclass(frozen=True)
class FixtureAdapter(RepositoryAdapter):
    observed_architecture: str = ""

    def validate(self, architecture: str) -> CheckResult:
        return CheckResult(check="fixture", passed=architecture == "docs/ARCHITECTURE.md")


def test_repository_facts_reach_only_downstream_adapter() -> None:
    manifest = load_manifest("template/signetum.toml")

    result = run_check(manifest, FixtureAdapter())

    assert result == CheckResult(check="fixture", passed=True)
