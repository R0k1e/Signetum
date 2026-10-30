# Generated from signetum.change.authority; edit the engine source and regenerate.
"""Check the standing of a named change specification without rewriting history."""

from pathlib import Path, PurePosixPath

from .change_models import (
    DecisionStatus,
    PlanStatus,
    ReviewStatus,
    SpecificationStatus,
    require_relative_path,
)
from .traceability_loading import load_decision, load_plan, load_review, load_specification


def validate_specification_authority(
    repository: Path, target: PurePosixPath, *, root: str, decisions: str, approved: bool
) -> None:
    relative = target.relative_to(PurePosixPath(root))
    if len(relative.parts) != 3 or relative.parts[1] != "specs" or target.suffix != ".toml":
        raise ValueError("resolution target is not a change specification")
    change_id = relative.parts[0]
    package = PurePosixPath(root) / change_id
    specification = load_specification(repository / target)
    review = load_review(repository / package / "review.toml")
    if (
        review.id != change_id
        or specification.review.id != change_id
        or not specification.id.startswith(change_id + "/")
    ):
        raise ValueError("resolution specification and Review identities disagree")
    plan_path = require_relative_path(specification.plan)
    if not plan_path.is_relative_to(package / "plans") or not (
        repository / plan_path
    ).resolve().is_relative_to(repository.resolve()):
        raise ValueError("resolution specification Plan is outside its package")
    plan = load_plan(repository / plan_path, change_id)
    if plan.specification not in (specification.id, target.as_posix()):
        raise ValueError("resolution specification Plan names another specification")
    if not approved:
        if review.status not in {
            ReviewStatus.DRAFT,
            ReviewStatus.ACTIVE,
            ReviewStatus.APPROVED,
        } or specification.status not in {SpecificationStatus.DRAFT, SpecificationStatus.APPROVED}:
            raise ValueError("resolution requires an active specification")
        return
    if (
        specification.status != SpecificationStatus.APPROVED
        or not specification.implementation_authorized
        or review.status in {ReviewStatus.DRAFT, ReviewStatus.ACTIVE}
        or plan.status != PlanStatus.APPROVED
    ):
        raise ValueError("resolution requires an approved specification and Plan")
    for reference in specification.decisions:
        decision = require_relative_path(reference)
        if not decision.is_relative_to(PurePosixPath(decisions)) or not (
            repository / decision
        ).resolve().is_relative_to(repository.resolve()):
            raise ValueError("resolution specification decision is outside its authority")
        if load_decision(repository / decision, reference).status != DecisionStatus.ACCEPTED:
            raise ValueError("resolution specification decision is not accepted")
