"""Repository-owned delivery settings, separate from executable validation settings."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from signetum.git import git_output
from signetum.manifest import ManifestError


class DeliveryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    branch: str = Field(min_length=1)


def delivery_policy(repository: Path) -> DeliveryPolicy:
    path = repository / ".agents/repo-dev/repo.yaml"
    try:
        document = TypeAdapter(dict[str, object]).validate_python(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        policy = DeliveryPolicy.model_validate(document["delivery"])
    except (OSError, KeyError, yaml.YAMLError, ValidationError) as error:
        raise ManifestError(
            f"delivery authority is unavailable or invalid: {path}: {error}"
        ) from error
    git_output(repository, "check-ref-format", "--branch", policy.branch)
    return policy
