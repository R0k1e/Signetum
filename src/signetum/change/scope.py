"""Change ownership derived from committed paths, never from commit prose."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from signetum.change.models import (
    DecisionStatus,
    Review,
    ReviewStatus,
    Specification,
    SpecificationStatus,
)
from signetum.change.paths import changes_root
from signetum.change_record import ChangeRecord, contract_digest, parse_change_record
from signetum.decision_identity import numbered_targets
from signetum.git import GitError, git_output, run_git
from signetum.manifest import RepositoryManifest
from signetum.operations import OperationError
from signetum.source_authority import committed_blob
from signetum.synchronization import member_contribution_paths
from signetum.traceability.loading import parse_decision, parse_review, parse_specification


class ChangeError(OperationError):
    """A change cannot establish its approved ownership or delivery scope."""


@dataclass(frozen=True)
class PreviousChange:
    change_id: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class DeliveryScope:
    first_delivered: tuple[str, ...]
    previously_delivered: tuple[PreviousChange, ...]


def delivery_scope(
    repository: Path,
    manifest: RepositoryManifest,
    base: str,
    tip: str,
    *,
    paths: tuple[str, ...] | None = None,
) -> DeliveryScope:
    root = changes_root(manifest)
    prefix = PurePosixPath(root).parts
    if paths is None:
        changed = git_output(
            repository,
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            base,
            tip,
            "--",
            root,
            strip=False,
        )
        paths = tuple(filter(None, changed.split("\0")))
    grouped: dict[str, list[str]] = {}
    for path in paths:
        parts = PurePosixPath(path).parts
        if parts[: len(prefix)] == prefix and len(parts) > len(prefix) + 1:
            grouped.setdefault(parts[len(prefix)], []).append(path)
    first: list[str] = []
    previous: list[PreviousChange] = []
    for change_id, change_paths in sorted(grouped.items()):
        held = git_output(
            repository, "ls-tree", "-d", "--name-only", base, "--", f"{root}/{change_id}"
        )
        if held:
            previous.append(PreviousChange(change_id, tuple(sorted(change_paths))))
        else:
            first.append(change_id)
    return DeliveryScope(tuple(first), tuple(previous))


def member_scope(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str
) -> DeliveryScope:
    return delivery_scope(
        repository, manifest, base, tip, paths=member_contribution_paths(repository, base, tip)
    )


def delivered_plans(
    repository: Path, manifest: RepositoryManifest, change_ids: tuple[str, ...], tip: str
) -> tuple[str, ...]:
    root = changes_root(manifest)
    result: list[str] = []
    for change_id in change_ids:
        if git_output(
            repository, "ls-tree", "--name-only", tip, "--", f"{root}/{change_id}/change.toml"
        ):
            read_package(repository, manifest, change_id, tip)
            result.append(f"{root}/{change_id}/change.toml")
        else:
            result.extend(
                path
                for path in git_output(
                    repository,
                    "ls-tree",
                    "-r",
                    "--name-only",
                    tip,
                    "--",
                    f"{root}/{change_id}/plans",
                ).splitlines()
                if path.endswith(".md")
            )
    return tuple(result)


def changed_commitments(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str, scope: DeliveryScope
) -> tuple[str, ...]:
    """Refuse rewritten delivered requirements, allowing exact numbering substitutions."""

    depth = len(PurePosixPath(changes_root(manifest)).parts) + 1
    paths = tuple(
        path
        for previous in scope.previously_delivered
        for path in previous.paths
        if PurePosixPath(path).parts[depth] in {"review.toml", "specs", "change.toml"}
    )
    if not paths:
        return ()
    rewrites = [
        (PurePosixPath(old).name, PurePosixPath(new).name)
        for old, new in numbered_targets(
            repository, base, tip, manifest.repository.decisions
        ).items()
    ]
    changed: list[str] = []
    for path in paths:
        before = run_git(repository, "show", f"{base}:{path}")
        after = run_git(repository, "show", f"{tip}:{path}")
        if path.endswith("/change.toml") and not before.returncode and not after.returncode:
            try:
                old_record = parse_change_record(before.stdout)
                new_record = parse_change_record(after.stdout)
            except ValueError as error:
                raise ChangeError(f"invalid delivered change record: {path}: {error}") from error
            if (
                old_record.id != new_record.id
                or old_record.source != new_record.source
                or old_record.contract != new_record.contract
                or old_record.approval != new_record.approval
                or git_output(repository, "diff", "--summary", base, tip, "--", path)
            ):
                changed.append(path)
            continue
        normalized = before.stdout
        for old, new in rewrites:
            normalized = normalized.replace(old, new)
        if (
            before.returncode
            or after.returncode
            or normalized != after.stdout
            or git_output(repository, "diff", "--summary", base, tip, "--", path)
        ):
            changed.append(path)
    return tuple(changed)


@dataclass(frozen=True)
class ChangePackage:
    review: Review
    specifications: tuple[tuple[str, Specification], ...]
    unaccepted_decisions: tuple[str, ...] = ()

    def require_approval(self) -> None:
        if self.unaccepted_decisions:
            raise ChangeError(
                f"change {self.review.id} requires an accepted decision: "
                + ", ".join(self.unaccepted_decisions)
            )
        if self.review.status != ReviewStatus.APPROVED or not self.specifications:
            raise ChangeError(f"change {self.review.id} is not implementation-authorized")
        if any(
            spec.status != SpecificationStatus.APPROVED or not spec.implementation_authorized
            for _, spec in self.specifications
        ):
            raise ChangeError(f"change {self.review.id} is not implementation-authorized")


@dataclass(frozen=True)
class ConsolidatedPackage:
    record: ChangeRecord

    def require_approval(self) -> None:
        if self.record.status != "active" or self.record.approval is None:
            raise ChangeError(f"change {self.record.id} is not implementation-authorized")


def read_package(
    repository: Path, manifest: RepositoryManifest, change_id: str, revision: str
) -> ChangePackage | ConsolidatedPackage:
    root = f"{changes_root(manifest)}/{change_id}"
    try:
        source = committed_blob(repository, revision, f"{root}/change.toml")
        if source is not None:
            legacy = git_output(
                repository,
                "ls-tree",
                "-r",
                "--name-only",
                revision,
                "--",
                f"{root}/review.toml",
                f"{root}/specs",
                f"{root}/plans",
            )
            if legacy:
                raise ValueError("change has competing consolidated and legacy authorities")
            record = parse_change_record(source[1])
            if record.id != change_id:
                raise ValueError("consolidated record declares another change identity")
            return ConsolidatedPackage(record)
        review = parse_review(git_output(repository, "show", f"{revision}:{root}/review.toml"))
        specifications = tuple(
            (path, parse_specification(git_output(repository, "show", f"{revision}:{path}")))
            for path in git_output(
                repository, "ls-tree", "-r", "--name-only", revision, "--", f"{root}/specs"
            ).splitlines()
            if path.endswith(".toml")
        )
    except (GitError, ValueError, KeyError) as error:
        raise ChangeError(
            f"change {change_id} package is unavailable or invalid: {error}"
        ) from error
    if review.id != change_id:
        raise ChangeError(f"change {change_id} Review declares a different identity: {review.id}")
    for _, specification in specifications:
        if specification.review.id != change_id:
            raise ChangeError(f"specification in {change_id} claims another Review")
        if not specification.plan.startswith(f"{root}/plans/"):
            raise ChangeError(f"specification in {change_id} names a Plan outside its package")
        if run_git(repository, "cat-file", "-e", f"{revision}:{specification.plan}").returncode:
            raise ChangeError(f"change {change_id} is missing its declared Plan")
    unaccepted: list[str] = []
    for _, specification in specifications:
        for reference in specification.decisions:
            content = run_git(repository, "show", f"{revision}:{reference}")
            if content.returncode:
                unaccepted.append(reference)
            elif parse_decision(content.stdout, reference).status != DecisionStatus.ACCEPTED:
                unaccepted.append(reference)
    return ChangePackage(review, specifications, tuple(sorted(set(unaccepted))))


def require_member_changes(
    repository: Path,
    manifest: RepositoryManifest,
    base: str,
    tip: str,
    ledger_changes: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Judge own implementation after approval in the package's one branch."""

    scope = member_scope(repository, manifest, base, tip)
    carried = tuple(
        sorted(
            set(
                (
                    *scope.first_delivered,
                    *(item.change_id for item in scope.previously_delivered),
                    *ledger_changes,
                )
            )
        )
    )
    required_contracts: dict[str, str] = {}
    for change_id in carried:
        package = read_package(repository, manifest, change_id, tip)
        package.require_approval()
        if isinstance(package, ConsolidatedPackage):
            if package.record.contract.approved_base != base:
                raise ChangeError(
                    "consolidated approval does not match the registered workspace base"
                )
            required_contracts[change_id] = contract_digest(package.record.contract)
    commits = tuple(
        git_output(
            repository, "rev-list", "--reverse", "--first-parent", "--no-merges", f"{base}..{tip}"
        ).splitlines()
    )
    if not commits:
        raise ChangeError("member has no own implementation commits")
    if not carried:
        raise ChangeError("member requires an approved change package")
    root = changes_root(manifest) + "/"
    decisions = manifest.repository.decisions.rstrip("/") + "/"
    approved = False
    for commit in (base, *commits):
        if approved:
            paths = git_output(
                repository, "diff-tree", "--no-commit-id", "--name-only", "-r", commit
            ).splitlines()
            if any(not path.startswith((root, decisions)) for path in paths):
                return carried
        try:
            for change_id in carried:
                package = read_package(repository, manifest, change_id, commit)
                package.require_approval()
                if change_id in required_contracts and (
                    not isinstance(package, ConsolidatedPackage)
                    or contract_digest(package.record.contract) != required_contracts[change_id]
                ):
                    raise ChangeError("earlier approval does not bind the current contract")
        except ChangeError:
            approved = False
            continue
        approved = True
    raise ChangeError("member is plan stage: no own implementation commit follows approval")
