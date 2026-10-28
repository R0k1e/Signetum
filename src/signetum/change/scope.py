"""Change ownership derived from committed paths, never from commit prose."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath

from signetum.change.models import (
    DecisionStatus,
    Review,
    ReviewStatus,
    Specification,
    SpecificationStatus,
)
from signetum.decision_identity import numbered_targets
from signetum.git import GitError, git_output, run_git
from signetum.manifest import ManifestError, RepositoryManifest
from signetum.operations import OperationError
from signetum.synchronization import verified_syncs
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


def changes_root(manifest: RepositoryManifest) -> str:
    """Resolve the package root from the declared per-change specification glob."""

    parts = PurePosixPath(manifest.repository.specifications).parts
    try:
        position = parts.index("*")
    except ValueError as error:
        raise ManifestError("specification authority must declare per-change packages") from error
    if position == 0:
        raise ManifestError("specification authority has no repository-owned change root")
    return PurePosixPath(*parts[:position]).as_posix()


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
            "--diff-filter=d",
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


def member_contribution_paths(repository: Path, base: str, tip: str) -> tuple[str, ...]:
    @cache
    def changed_between(before: str, after: str) -> frozenset[str]:
        return frozenset(
            filter(
                None,
                git_output(
                    repository,
                    "diff",
                    "--name-only",
                    "-z",
                    "--no-renames",
                    before,
                    after,
                    strip=False,
                ).split("\0"),
            )
        )

    owned: set[str] = set()
    inherited: dict[str, str] = {}
    synchronized = dict(verified_syncs(repository, base, tip))
    history = git_output(
        repository, "log", "--first-parent", "--reverse", "--format=%H%x09%P", f"{base}..{tip}"
    )
    for entry in history.splitlines():
        commit, _, raw_parents = entry.partition("\t")
        parents = raw_parents.split()
        before = parents[0] if parents else base
        touched = changed_between(before, commit)
        if source := synchronized.get(commit):
            from_source = changed_between(source, commit)
            for path in touched | changed_between(before, source) | owned:
                if path not in from_source:
                    inherited[path] = source
                    owned.discard(path)
                elif path in touched:
                    inherited[path] = source
                    owned.add(path)
                elif path in owned:
                    inherited[path] = source
            continue
        by_authority: dict[str, set[str]] = defaultdict(set)
        for path in touched:
            by_authority[inherited.get(path, base)].add(path)
        for reference, paths in by_authority.items():
            differences = changed_between(reference, commit)
            owned.difference_update(paths - differences)
            owned.update(paths & differences)
    return tuple(sorted(owned))


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
    return tuple(
        path
        for change_id in change_ids
        for path in git_output(
            repository, "ls-tree", "-r", "--name-only", tip, "--", f"{root}/{change_id}/plans"
        ).splitlines()
        if path.endswith(".md")
    )


def changed_commitments(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str, scope: DeliveryScope
) -> tuple[str, ...]:
    """Refuse rewritten delivered requirements, allowing exact numbering substitutions."""

    depth = len(PurePosixPath(changes_root(manifest)).parts) + 1
    paths = tuple(
        path
        for previous in scope.previously_delivered
        for path in previous.paths
        if PurePosixPath(path).parts[depth] in {"review.toml", "specs"}
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


def read_package(
    repository: Path, manifest: RepositoryManifest, change_id: str, revision: str
) -> ChangePackage:
    root = f"{changes_root(manifest)}/{change_id}"
    try:
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
    for change_id in carried:
        read_package(repository, manifest, change_id, tip).require_approval()
    commits = tuple(
        git_output(
            repository, "rev-list", "--reverse", "--first-parent", "--no-merges", f"{base}..{tip}"
        ).splitlines()
    )
    if not commits:
        raise ChangeError("member has no own implementation commits")
    if not carried:
        return carried
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
                read_package(repository, manifest, change_id, commit).require_approval()
        except ChangeError:
            continue
        approved = True
    raise ChangeError("member is plan stage: no own implementation commit follows approval")
