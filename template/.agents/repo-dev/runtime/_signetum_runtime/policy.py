# Generated from signetum.policy; edit the engine source and regenerate.
"""Repository-owned delivery settings, separate from executable validation settings."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from .contract_values import FrozenContract
from .git import git_output
from .manifest import ManifestError
from .serialization import Constraints, dataclass_from_mapping
from .vendor_yaml import YAMLError, safe_load


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
