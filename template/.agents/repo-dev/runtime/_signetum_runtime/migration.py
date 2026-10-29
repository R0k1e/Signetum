# Generated from signetum.migration; edit the engine source and regenerate.
"""Read-only, source-bound inventory and explicit legacy clause mapping previews."""

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from .change_models import (
    ClauseDisposition,
    ClauseId,
    Decision,
    DecisionStatus,
    Plan,
    Review,
    Specification,
    complete_decision_replacements,
    require_relative_path,
)
from .change_record import Digest
from .contract_values import FrozenContract
from .decision_clauses import ClauseRevision, Text
from .decision_history import TopicRevision
from .development_log import ObjectId
from .git import git_output, run_git
from .operation_cli import OperationParser, utility_failure
from .serialization import Constraints, contract_mapping, dataclass_from_mapping, load_json
from .source_authority import (
    authority_roots,
    committed_blob,
    committed_blob_identity,
    require_ancestor,
    require_committed_bindings,
)
from .traceability_boundary import RepositoryInventory, TraceabilityManifest
from .traceability_loading import (
    parse_decision,
    parse_plan,
    parse_review,
    parse_specification,
)
from .traceability_validator import TraceabilityValidator, decision_corpus_issues


@dataclass(frozen=True, kw_only=True)
class SourceDocument(FrozenContract):
    path: Text
    blob: ObjectId
    kind: Literal["review", "specification", "plan", "decision"]
    status: Text


@dataclass(frozen=True, kw_only=True)
class MigrationIssue(FrozenContract):
    path: Text
    code: Text
    reason: Text


@dataclass(frozen=True, kw_only=True)
class LegacyReview(FrozenContract):
    path: Text
    value: Review


@dataclass(frozen=True, kw_only=True)
class LegacySpecification(FrozenContract):
    path: Text
    value: Specification


@dataclass(frozen=True, kw_only=True)
class LegacyPlan(FrozenContract):
    path: Text
    value: Plan


@dataclass(frozen=True, kw_only=True)
class LegacyDecision(FrozenContract):
    path: Text
    value: Decision


@dataclass(frozen=True, kw_only=True)
class LegacyRequirement(FrozenContract):
    review: Text
    clause_id: ClauseId
    specification: Text | None
    acceptance_indices: tuple[int, ...]
    ambiguous: bool


@dataclass(frozen=True, kw_only=True)
class MigrationInventory(FrozenContract):
    schema_version: Literal[1] = 1
    commit: ObjectId
    digest: Digest
    manifest_blob: ObjectId | None
    change_root: Text
    decision_root: Text
    documents: tuple[SourceDocument, ...]
    reviews: tuple[LegacyReview, ...]
    specifications: tuple[LegacySpecification, ...]
    plans: tuple[LegacyPlan, ...]
    decisions: tuple[LegacyDecision, ...]
    requirements: tuple[LegacyRequirement, ...]
    issues: tuple[MigrationIssue, ...]


@dataclass(frozen=True, kw_only=True)
class SourceSpan(FrozenContract):
    path: Text
    start_line: Annotated[int, Constraints(minimum=1)]
    end_line: Annotated[int, Constraints(minimum=1)]


@dataclass(frozen=True, kw_only=True)
class ClauseMapping(FrozenContract):
    sources: Annotated[tuple[SourceSpan, ...], Constraints(min_length=1)]
    clause: ClauseRevision
    reason: Text


@dataclass(frozen=True, kw_only=True)
class MigrationProposal(FrozenContract):
    schema_version: Literal[1]
    source_commit: ObjectId
    inventory_digest: Digest
    topics: tuple[TopicRevision, ...]
    clauses: tuple[ClauseMapping, ...]


@dataclass(frozen=True, kw_only=True)
class MappedClause(FrozenContract):
    sources: tuple[SourceSpan, ...]
    excerpts: tuple[Text, ...]
    clause: ClauseRevision
    reason: Text


@dataclass(frozen=True, kw_only=True)
class MigrationPreview(FrozenContract):
    status: Literal["unapproved"] = "unapproved"
    source_commit: ObjectId
    inventory_digest: Digest
    topics: tuple[TopicRevision, ...]
    clauses: tuple[MappedClause, ...]
    requires_review: tuple[Text, ...]
    unmapped: tuple[Text, ...]
    issues: tuple[MigrationIssue, ...]


def _kind(path: str, root: str, decisions: str) -> str | None:
    value = PurePosixPath(path)
    if value.is_relative_to(PurePosixPath(decisions)) and value.suffix == ".md":
        return "decision"
    if not value.is_relative_to(PurePosixPath(root)):
        return None
    parts = value.relative_to(root).parts
    if len(parts) == 2 and parts[1] == "review.toml":
        return "review"
    if len(parts) == 3 and parts[1] == "specs" and value.suffix == ".toml":
        return "specification"
    if len(parts) == 3 and parts[1] == "plans" and value.suffix == ".md":
        return "plan"
    return None


def _requirements(
    reviews: list[LegacyReview],
    specifications: list[LegacySpecification],
    issues: list[MigrationIssue],
) -> tuple[LegacyRequirement, ...]:
    results = []
    for review in reviews:
        for clause in review.value.clauses:
            if clause.disposition != ClauseDisposition.COVERED:
                issues.append(
                    MigrationIssue(
                        path=review.path,
                        code="explicit_disposition_mapping",
                        reason=(
                            f"Preserve {clause.id}'s {clause.disposition.value} "
                            "disposition and authority explicitly."
                        ),
                    )
                )
                continue
            owners = [
                item
                for item in specifications
                if item.value.review.id == review.value.id
                and clause.id in item.value.review.clauses
                and item.value.id == clause.specification
                and PurePosixPath(item.path).parent == PurePosixPath(review.path).parent / "specs"
                and item.value.id.startswith(review.value.id + "/")
                and item.value.schema_version == review.value.schema_version == 1
            ]
            selected = ()
            if len(owners) == 1:
                spec = owners[0]
                acceptance = spec.value.extensions.get("acceptance", [])
                if isinstance(acceptance, list) and all(
                    isinstance(item, str) and item for item in acceptance
                ):
                    if len(spec.value.review.clauses) == 1:
                        selected = tuple(range(len(acceptance)))
                    elif (
                        acceptance.count(clause.statement) == 1
                        and sum(
                            other.statement == clause.statement
                            for other in review.value.clauses
                            if other.id in spec.value.review.clauses
                        )
                        == 1
                    ):
                        selected = (acceptance.index(clause.statement),)
            if not selected:
                issues.append(
                    MigrationIssue(
                        path=review.path,
                        code="ambiguous_acceptance",
                        reason=(
                            f"{clause.id} needs an explicit acceptance mapping; "
                            "no positional pairing is inferred."
                        ),
                    )
                )
            results.append(
                LegacyRequirement(
                    review=review.path,
                    clause_id=clause.id,
                    specification=owners[0].path if len(owners) == 1 else None,
                    acceptance_indices=selected,
                    ambiguous=not selected,
                )
            )
    for specification in specifications:
        acceptance = specification.value.extensions.get("acceptance", [])
        if isinstance(acceptance, list):
            assigned = {
                index
                for item in results
                if item.specification == specification.path
                for index in item.acceptance_indices
            }
            if set(range(len(acceptance))) - assigned:
                issues.append(
                    MigrationIssue(
                        path=specification.path,
                        code="unassigned_acceptance",
                        reason="Source acceptance entries need explicit clause mappings.",
                    )
                )
    return tuple(results)


def inventory(repository: Path, commit: str = "HEAD") -> MigrationInventory:
    if commit != "HEAD" and re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", commit) is None:
        raise ValueError("migration inventory requires HEAD or an exact commit identity")
    source = git_output(repository, "rev-parse", "--verify", f"{commit}^{{commit}}")
    root, decision_root = authority_roots(repository, commit=source)
    manifest_blob = committed_blob_identity(repository, source, "signetum.toml")
    tree = git_output(
        repository, "ls-tree", "-r", "-z", source, "--", root, decision_root, strip=False
    )
    documents, reviews, specs, plans, decisions, issues = [], [], [], [], [], []
    for entry in sorted(item for item in tree.split("\0") if item):
        header, _, path = entry.partition("\t")
        mode, object_kind, blob_id = header.split()
        kind = _kind(path, root, decision_root)
        if kind is None:
            continue
        status = "invalid"
        try:
            if object_kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError("legacy authority is not a regular committed source file")
            blob = committed_blob(repository, source, path)
            if blob is None:
                raise ValueError("legacy source vanished from its committed tree")
            text = blob[1]
            if kind == "review":
                review = parse_review(text)
                if review.id != PurePosixPath(path).parent.name:
                    raise ValueError("legacy Review identity differs from its package")
                reviews.append(LegacyReview(path=path, value=review))
                status = review.status.value
            elif kind == "specification":
                specification = parse_specification(text)
                specs.append(LegacySpecification(path=path, value=specification))
                status = specification.status.value
            elif kind == "plan":
                plan = parse_plan(text, PurePosixPath(path).parts[-3], PurePosixPath(path))
                plans.append(LegacyPlan(path=path, value=plan))
                status = plan.status.value
                if re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", plan.approved_base) is None:
                    issues.append(
                        MigrationIssue(
                            path=path,
                            code="unresolved_base",
                            reason="Retain the unresolved legacy base verbatim; do not guess HEAD.",
                        )
                    )
                else:
                    try:
                        require_ancestor(repository, plan.approved_base, source)
                    except ValueError:
                        issues.append(
                            MigrationIssue(
                                path=path,
                                code="unverified_base",
                                reason="The legacy base is unavailable in this source ancestry.",
                            )
                        )
            else:
                decision = parse_decision(text, path)
                decisions.append(LegacyDecision(path=path, value=decision))
                status = decision.status.value
                issues.append(
                    MigrationIssue(
                        path=path,
                        code="explicit_clause_mapping",
                        reason="Review source selections, stable clause IDs and topic context.",
                    )
                )
        except (ValueError, OSError) as error:
            issues.append(MigrationIssue(path=path, code="invalid_source", reason=str(error)))
        documents.append(
            dataclass_from_mapping(
                SourceDocument,
                {
                    "path": path,
                    "blob": blob_id,
                    "kind": kind,
                    "status": status,
                },
            )
        )
    paths = git_output(repository, "ls-tree", "-r", "--name-only", "-z", source)
    source_inventory = RepositoryInventory(
        paths=frozenset(item for item in paths.split("\0") if item)
    )
    for review in reviews:
        package = PurePosixPath(review.path).parent
        report = TraceabilityValidator().validate(
            manifest=TraceabilityManifest(
                schema_version=1, changes_root=root, decision_roots=(decision_root,)
            ),
            inventory=source_inventory,
            review_path=review.path,
            review=review.value,
            specifications=tuple(
                (item.path, item.value)
                for item in specs
                if PurePosixPath(item.path).is_relative_to(package)
            ),
            plans=tuple(
                (item.path, item.value)
                for item in plans
                if PurePosixPath(item.path).is_relative_to(package)
            ),
            review_ids=frozenset(item.value.id for item in reviews),
            decisions=tuple((item.path, item.value) for item in decisions),
        )
        issues.extend(
            MigrationIssue(path=item.file, code=item.code, reason=item.reason)
            for item in report.issues
        )
    corpus = tuple((item.path, item.value) for item in decisions)
    issues.extend(
        MigrationIssue(path=item.file, code=item.code, reason=item.reason)
        for item in decision_corpus_issues(corpus)
    )
    counts = Counter(item.value.name for item in decisions)
    issues.extend(
        MigrationIssue(
            path=item.path,
            code="ambiguous_decision_identity",
            reason="The legacy basename is shared; preserve explicit path identity.",
        )
        for item in decisions
        if counts[item.value.name] > 1
    )
    requirements = _requirements(reviews, specs, issues)
    material = {
        "change_root": root,
        "decision_root": decision_root,
        "manifest_blob": manifest_blob,
        "documents": [contract_mapping(item) for item in documents],
    }
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return MigrationInventory(
        commit=source,
        digest=digest,
        manifest_blob=manifest_blob,
        change_root=root,
        decision_root=decision_root,
        documents=tuple(documents),
        reviews=tuple(reviews),
        specifications=tuple(specs),
        plans=tuple(plans),
        decisions=tuple(decisions),
        requirements=requirements,
        issues=tuple(issues),
    )


def parse_proposal(value: object) -> MigrationProposal:
    return dataclass_from_mapping(MigrationProposal, value, use_defaults=True)


def preview(repository: Path, proposal: MigrationProposal) -> MigrationPreview:
    original = inventory(repository, proposal.source_commit)
    current = inventory(repository)
    require_ancestor(repository, original.commit, current.commit)
    if proposal.inventory_digest != original.digest or original.digest != current.digest:
        raise ValueError("legacy authority inventory changed; review the mapping again")
    require_committed_bindings(repository, current.commit)
    dirty = run_git(
        repository,
        "diff",
        "--quiet",
        "--no-ext-diff",
        "--no-textconv",
        "HEAD",
        "--",
        current.change_root,
        current.decision_root,
    )
    if dirty.returncode != 0:
        raise ValueError("uncommitted authority changes cannot be included in a migration preview")
    identities = [item.clause.id for item in proposal.clauses]
    topics = {item.id for item in proposal.topics}
    if len(set(identities)) != len(identities) or len(topics) != len(proposal.topics):
        raise ValueError("migration clause and topic identities must be unique")
    source_decisions = {item.path: item.value for item in original.decisions}
    by_name = {item.name: item for item in source_decisions.values()}
    counts = Counter(item.name for item in source_decisions.values())
    mapped, selected = [], set()
    for item in proposal.clauses:
        if item.clause.topic not in topics:
            raise ValueError("migration clause has no explicit topic context")
        excerpts = []
        for span in item.sources:
            require_relative_path(span.path)
            decision = source_decisions.get(span.path)
            if decision is None:
                raise ValueError("mapping source is not an inventoried legacy decision")
            if any(counts[item.rsplit("/", 1)[-1]] > 1 for item in decision.superseded_by):
                raise ValueError(
                    "supersession identity is ambiguous; do not choose a source by order"
                )
            if item.clause.status == "active" and (
                decision.status != DecisionStatus.ACCEPTED
                or complete_decision_replacements(decision, by_name)
            ):
                raise ValueError(
                    "historical or unaccepted authority cannot silently become an active rule"
                )
            blob = committed_blob(repository, original.commit, span.path)
            if blob is None:
                raise ValueError("mapping source is absent")
            lines = blob[1].splitlines()
            if span.end_line < span.start_line or span.end_line > len(lines):
                raise ValueError("mapping source range is outside its exact legacy document")
            excerpt = "\n".join(lines[span.start_line - 1 : span.end_line])
            if not excerpt.strip():
                raise ValueError("mapping cannot select an empty source span")
            excerpts.append(excerpt)
            selected.add(span.path)
        mapped.append(
            MappedClause(
                sources=item.sources,
                excerpts=tuple(excerpts),
                clause=item.clause,
                reason=item.reason,
            )
        )
    return MigrationPreview(
        source_commit=original.commit,
        inventory_digest=original.digest,
        topics=proposal.topics,
        clauses=tuple(mapped),
        requires_review=tuple(sorted(source_decisions)),
        unmapped=tuple(sorted(set(source_decisions) - selected)),
        issues=tuple(item for item in original.issues if item.path in selected),
    )


def main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(description=__doc__)
    parser.add_argument("operation", choices=["inventory", "preview"])
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--proposal", type=Path)
    try:
        options = parser.parse_args(arguments)
        if options.operation == "inventory":
            if options.proposal is not None:
                raise ValueError("inventory does not consume a mapping proposal")
            result = inventory(options.repository)
        else:
            if options.proposal is None:
                raise ValueError("preview requires an explicit mapping proposal")
            result = preview(
                options.repository, parse_proposal(load_json(options.proposal.read_text()))
            )
    except (ValueError, OSError, TypeError) as error:
        return utility_failure("migration", error)
    print(
        json.dumps(
            {"schema_version": 1, "status": "preview", "result": contract_mapping(result)},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
