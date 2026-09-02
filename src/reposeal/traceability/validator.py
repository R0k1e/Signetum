"""Complete static relation validation for governed changes."""

from collections import Counter
from pathlib import PurePosixPath

from pydantic import Field

from reposeal.change.models import (
    AcceptanceResult,
    ClauseDisposition,
    Decision,
    DecisionStatus,
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


_REFUSED_DECISION_STATUSES = frozenset({DecisionStatus.REJECTED, DecisionStatus.DRAFT})


def decision_corpus_issues(
    decisions: tuple[tuple[str, Decision], ...],
) -> tuple[TraceabilityIssue, ...]:
    """Refuse a corpus where a supersession is recorded on one side only.

    A supersession which only the successor records leaves every reader of the
    superseded decision believing it still stands.
    """

    by_name = {decision.name: decision for _, decision in decisions}
    issues: list[TraceabilityIssue] = []
    for path, decision in decisions:
        for replaced in decision.supersedes:
            target = by_name.get(replaced.rsplit("/", 1)[-1])
            if target is None:
                issues.append(
                    TraceabilityIssue(
                        code="dangling-supersession",
                        file=path,
                        field="Supersedes",
                        reason=f"supersedes an absent decision: {replaced}",
                    )
                )
            elif decision.name not in {item.rsplit("/", 1)[-1] for item in target.superseded_by}:
                issues.append(
                    TraceabilityIssue(
                        code="one-sided-supersession",
                        file=target.path,
                        field="Superseded by",
                        reason=f"does not record its supersession by {decision.name}",
                    )
                )
    return tuple(issues)


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
        review_ids: frozenset[str] | None,
        decisions: tuple[tuple[str, Decision], ...],
    ) -> TraceabilityReport:
        decisions_by_path = {path: decision for path, decision in decisions}
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
        clauses_by_id = {clause.id: clause for clause in review.clauses}
        out_of_scope = {
            clause.id
            for clause in review.clauses
            if clause.disposition is ClauseDisposition.OUT_OF_SCOPE
        }
        approved = tuple(
            (path, specification)
            for path, specification in specifications
            if specification.status is SpecificationStatus.APPROVED
        )
        owners = Counter(
            clause for _, specification in approved for clause in specification.owned_clauses
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
                elif clauses_by_id[clause].specification != specification.id:
                    issues.append(
                        self._issue(
                            "ownership-mismatch",
                            path,
                            "specification.review.clauses",
                            f"Review does not assign {clause} to {specification.id}",
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
                expected = {
                    clause
                    for clause in specification.owned_clauses
                    if clauses_by_id.get(clause) is not None
                    and clauses_by_id[clause].disposition is ClauseDisposition.COVERED
                }
                for clause in sorted(expected - covered):
                    issues.append(
                        self._issue(
                            "missing-obligation",
                            specification.plan,
                            "plan.obligations",
                            f"no obligation covers {clause}",
                        )
                    )
                for clause in sorted(covered - expected):
                    issues.append(
                        self._issue(
                            "unexpected-obligation",
                            specification.plan,
                            "plan.obligations",
                            f"obligation covers non-owned or non-covered clause {clause}",
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
                    continue
                obtained = decisions_by_path.get(decision)
                if obtained is None:
                    issues.append(
                        self._issue(
                            "unreadable-decision",
                            path,
                            "specification.decisions",
                            f"decision was not loaded: {decision}",
                        )
                    )
                elif obtained.status in _REFUSED_DECISION_STATUSES:
                    # A proposal is the ordinary state of a decision while its
                    # own change is in flight, and final already refuses a tree
                    # holding one. Refuse only what delivery cannot catch.
                    issues.append(
                        self._issue(
                            "unaccepted-decision",
                            path,
                            "specification.decisions",
                            f"decision {decision} declares status {obtained.status.value}",
                        )
                    )
                elif obtained.superseded_by:
                    replacement = ", ".join(obtained.superseded_by)
                    issues.append(
                        self._issue(
                            "superseded-decision",
                            path,
                            "specification.decisions",
                            f"decision {decision} was superseded by {replacement}",
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

        for clause in review.clauses:
            if clause.disposition in {
                ClauseDisposition.COVERED,
                ClauseDisposition.DEFERRED,
            }:
                if clause.specification is None or clause.specification not in specification_by_id:
                    issues.append(
                        self._issue(
                            "missing-specification",
                            review_path,
                            "review.clauses",
                            f"{clause.id} has no existing Specification",
                        )
                    )
                if clause.reason is not None:
                    issues.append(
                        self._issue(
                            "unexpected-disposition-reason",
                            review_path,
                            "review.clauses",
                            f"{clause.id} is not out of scope",
                        )
                    )
            else:
                if clause.reason is None or not clause.reason.strip():
                    issues.append(
                        self._issue(
                            "missing-out-of-scope-reason",
                            review_path,
                            "review.clauses",
                            f"{clause.id} requires a reason",
                        )
                    )
                if clause.specification is not None or owners[clause.id]:
                    issues.append(
                        self._issue(
                            "out-of-scope-owned",
                            review_path,
                            "review.clauses",
                            f"{clause.id} must not have a Specification owner",
                        )
                    )
            if clause.disposition is ClauseDisposition.DEFERRED and review.status.value in {
                "complete",
                "completed",
                "closed",
            }:
                issues.append(
                    self._issue(
                        "unresolved-deferral",
                        review_path,
                        "review.clauses",
                        f"completed Review still defers {clause.id}",
                    )
                )

        for clause in sorted(clause_ids - out_of_scope):
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
        acceptance = review.acceptance
        if acceptance.result is AcceptanceResult.PENDING:
            if (
                acceptance.delivery_commit
                or acceptance.accepted_clauses
                or acceptance.rejected_clauses
            ):
                issues.append(
                    self._issue(
                        "invalid-pending-acceptance",
                        review_path,
                        "review.acceptance",
                        "pending acceptance cannot claim delivery results",
                    )
                )
        else:
            if not acceptance.delivery_commit:
                issues.append(
                    self._issue(
                        "acceptance-without-delivery",
                        review_path,
                        "review.acceptance.delivery_commit",
                        "acceptance requires a delivery identity",
                    )
                )
            decided = set(acceptance.accepted_clauses) | set(acceptance.rejected_clauses)
            unknown = decided - clause_ids
            for clause in sorted(unknown):
                issues.append(
                    self._issue(
                        "unknown-acceptance-clause",
                        review_path,
                        "review.acceptance",
                        clause,
                    )
                )
            if set(acceptance.accepted_clauses) & set(acceptance.rejected_clauses):
                issues.append(
                    self._issue(
                        "conflicting-acceptance",
                        review_path,
                        "review.acceptance",
                        "a clause cannot be accepted and rejected",
                    )
                )
            if acceptance.result in {AcceptanceResult.REJECTED, AcceptanceResult.REOPENED}:
                if not acceptance.rejected_clauses or not acceptance.linked_change:
                    issues.append(
                        self._issue(
                            "missing-linked-change",
                            review_path,
                            "review.acceptance.linked_change",
                            "rejected or reopened clauses require a new linked Change",
                        )
                    )
                elif acceptance.linked_change == review.id or (
                    review_ids is not None and acceptance.linked_change not in review_ids
                ):
                    issues.append(
                        self._issue(
                            "dangling-linked-change",
                            review_path,
                            "review.acceptance.linked_change",
                            "continuation must name another active TOML Change",
                        )
                    )
            elif acceptance.linked_change is not None:
                issues.append(
                    self._issue(
                        "unexpected-linked-change",
                        review_path,
                        "review.acceptance.linked_change",
                        "accepted result cannot link a continuation Change",
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
