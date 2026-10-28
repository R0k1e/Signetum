"""Repository-owned delivery settings, separate from executable validation settings."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from yaml import YAMLError, safe_load

from signetum.contract_values import FrozenContract
from signetum.git import git_output
from signetum.manifest import ManifestError
from signetum.serialization import Constraints, dataclass_from_mapping


@dataclass(frozen=True, kw_only=True)
class DeliveryPolicy(FrozenContract):
    branch: Annotated[str, Constraints(min_length=1)]


def delivery_policy(repository: Path) -> DeliveryPolicy:
    path = repository / ".agents/repo-dev/repo.yaml"
    try:
        document = safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("repository policy must be an object")
        policy = dataclass_from_mapping(DeliveryPolicy, document["delivery"])
    except (OSError, KeyError, YAMLError, ValueError) as error:
        raise ManifestError(
            f"delivery authority is unavailable or invalid: {path}: {error}"
        ) from error
    git_output(repository, "check-ref-format", "--branch", policy.branch)
    return policy
