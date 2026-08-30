"""Complete static relation validation for governed changes."""

from collections import Counter
from pathlib import PurePosixPath

from pydantic import Field

from reposeal.change.models import (
    FrozenModel,
    Plan,
    Review,
    Specification,
    SpecificationStatus,
)
from reposeal.traceability.boundary import (
    RepositoryInventory,
    TraceabilityManifest,
)


class TraceabilityIssue(FrozenModel):
    code: str
    file: str
    field: str
    reason: str


class TraceabilityReport(FrozenModel):
    schema_version: int = Field(default=1)
    valid: bool
    issues: tuple[TraceabilityIssue, ...]


class TraceabilityValidator:
    """Validate closure without filesystem traversal or evidence interpretation."""

    def validate(
        self,
        manifest: TraceabilityManifest,
        inventory: RepositoryInventory,
        review_path: str,
        review: Review,
        specifications: tuple[tuple[str, Specification], ...],
        plans: tuple[tuple[str, Plan], ...],
    ) -> TraceabilityReport:
        issues: list[TraceabilityIssue] = []
        if review.schema_version != 1:
            issues.append(
                self._issue(
                    "unsupported-schema",
                    review_path,
                    "review.schema_version",
                    "unsupported schema major",
                )
            )

        clause_ids = {clause.id for clause in review.clauses}
        exclusions = {exclusion.clause for exclusion in review.exclusions}
        approved = tuple(
            (path, specification)
            for path, specification in specifications
            if specification.status is SpecificationStatus.APPROVED
        )
        owners = Counter(
            clause
            for _, specification in approved
            for clause in specification.owned_clauses
            if clause not in {deferral.clause for deferral in specification.deferrals}
        )
        specification_by_id = {
            specification.id: specification for _, specification in specifications
        }
        plans_by_path = {path: plan for path, plan in plans}

        for path, specification in specifications:
            if specification.schema_version != 1:
                issues.append(
                    self._issue(
                        "unsupported-schema",
                        path,
                        "specification.schema_version",
                        "unsupported schema major",
                    )
                )
            if specification.review.id != review.id:
                issues.append(
                    self._issue(
                        "unknown-review",
                        path,
                        "specification.review.id",
                        "Specification names another Review",
                    )
                )
            for clause in specification.owned_clauses:
                if clause not in clause_ids:
                    issues.append(
                        self._issue(
                            "unknown-clause",
                            path,
                            "specification.review.clauses",
                            f"unknown clause {clause}",
                        )
                    )
            if (
                specification.status is SpecificationStatus.SUPERSEDED
                and specification.owned_clauses
            ):
                issues.append(
                    self._issue(
                        "superseded-owner",
                        path,
                        "specification.review.clauses",
                        "superseded Specification owns clauses",
                    )
                )
            if not inventory.contains(specification.plan):
                issues.append(
                    self._issue(
                        "dangling-plan",
                        path,
                        "specification.plan",
                        "Plan reference is absent",
                    )
                )
            elif specification.plan not in plans_by_path:
                issues.append(
                    self._issue(
                        "unparsed-plan",
                        path,
                        "specification.plan",
                        "referenced Plan was not loaded",
                    )
                )
            else:
                plan = plans_by_path[specification.plan]
                if plan.specification != path:
                    issues.append(
                        self._issue(
                            "wrong-plan-owner",
                            specification.plan,
                            "plan.specification",
                            "Plan refers to another Specification",
                        )
                    )
                covered = {
                    clause for obligation in plan.obligations for clause in obligation.clauses
                }
                for clause in specification.owned_clauses:
                    if clause not in covered and clause not in {
                        item.clause for item in specification.deferrals
                    }:
                        issues.append(
                            self._issue(
                                "missing-obligation",
                                specification.plan,
                                "plan.obligations",
                                f"no obligation covers {clause}",
                            )
                        )
            for decision in specification.decisions:
                if not inventory.contains(decision):
                    issues.append(
                        self._issue(
                            "dangling-decision",
                            path,
                            "specification.decisions",
                            f"missing decision {decision}",
                        )
                    )
            for deferral in specification.deferrals:
                target = specification_by_id.get(deferral.target_specification)
                if target is None or target.status is not SpecificationStatus.APPROVED:
                    issues.append(
                        self._issue(
                            "invalid-deferral",
                            path,
                            "specification.deferrals",
                            f"invalid target {deferral.target_specification}",
                        )
                    )

        for clause in sorted(clause_ids - exclusions):
            count = owners[clause]
            if count != 1:
                code = "missing-owner" if count == 0 else "duplicate-owner"
                issues.append(
                    self._issue(
                        code,
                        review_path,
                        "review.clauses",
                        f"{clause} has {count} current owners",
                    )
                )
        for clause in exclusions:
            if clause not in clause_ids:
                issues.append(
                    self._issue(
                        "unknown-exclusion",
                        review_path,
                        "review.exclusions",
                        f"unknown clause {clause}",
                    )
                )
        accepted_deliveries = {
            clause: acceptance.delivery_commit
            for acceptance in review.acceptances
            for clause in acceptance.accepted_clauses
        }
        for reopen in review.reopenings:
            if accepted_deliveries.get(reopen.clause) != reopen.delivery_commit:
                issues.append(
                    self._issue(
                        "invalid-reopen",
                        review_path,
                        "review.reopenings",
                        "reopen has no matching prior acceptance",
                    )
                )
        for root in manifest.legacy_roots:
            current = inventory.below(root)
            baseline = frozenset(
                path
                for path in manifest.legacy_inventory
                if PurePosixPath(path).is_relative_to(PurePosixPath(root))
            )
            for added in sorted(current - baseline):
                issues.append(
                    self._issue(
                        "legacy-addition",
                        added,
                        "inventory",
                        "new file under a declared legacy root",
                    )
                )
        return TraceabilityReport(valid=not issues, issues=tuple(issues))

    @staticmethod
    def _issue(code: str, file: str, field: str, reason: str) -> TraceabilityIssue:
        return TraceabilityIssue(code=code, file=file, field=field, reason=reason)
