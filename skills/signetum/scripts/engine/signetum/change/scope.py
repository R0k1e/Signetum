"""Change ownership derived from committed paths, never from commit prose."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Literal

from signetum.change.paths import changes_root, is_record_path
from signetum.change_record import (
    ChangeRecord,
    competing_legacy_authorities,
    contract_digest,
    parse_change_record,
)
from signetum.decision_identity import numbered_targets
from signetum.development_store import DevelopmentReviewError, decision_application_commits
from signetum.git import GitError, git_output, run_git
from signetum.manifest import RepositoryManifest, parse_bindings
from signetum.operations import OperationError
from signetum.source_authority import committed_blob
from signetum.synchronization import member_contribution_paths
from signetum.workspaces import WorkspaceRecord, branch_name, read_record, state_root


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
    # Raw history below the change root is not an executable approval package.
    # Inspect both snapshots so removing a current authority cannot hide its scope.
    authority_packages: set[str] = set()
    current_packages: set[str] = set()
    for revision in (base, tip):
        for path in git_output(
            repository, "ls-tree", "-r", "--name-only", revision, "--", root
        ).splitlines():
            candidate = PurePosixPath(path)
            parts = candidate.parts
            if parts[: len(prefix)] != prefix or len(parts) <= len(prefix) + 1:
                continue
            if len(parts) == len(prefix) + 2 and candidate.name == "change.toml":
                current_packages.add(parts[len(prefix)])
                authority_packages.add(parts[len(prefix)])
            elif (
                len(parts) == len(prefix) + 2 and candidate.name == "review.toml"
            ) or candidate.match(f"{root}/*/specs/*.toml"):
                # Historical promises remain protected without authorizing new work.
                authority_packages.add(parts[len(prefix)])
    first: list[str] = []
    previous: list[PreviousChange] = []
    for change_id, change_paths in sorted(grouped.items()):
        if change_id not in authority_packages:
            continue
        held = git_output(
            repository, "ls-tree", "-d", "--name-only", base, "--", f"{root}/{change_id}"
        )
        if held:
            previous.append(PreviousChange(change_id, tuple(sorted(change_paths))))
        elif change_id in current_packages:
            first.append(change_id)
    return DeliveryScope(tuple(first), tuple(previous))


def records_only(repository: Path, root: str, older: str, newer: str) -> bool:
    """Whether ``older..newer`` changes only change records, keeping every contract.

    Such a range changes no input a check reads beyond source admission, so
    evidence of ``older`` still describes ``newer``.
    """
    if run_git(repository, "merge-base", "--is-ancestor", older, newer).returncode:
        return False
    paths = tuple(
        filter(
            None,
            git_output(
                repository, "diff", "--name-only", "-z", "--no-renames", older, newer, strip=False
            ).split("\0"),
        )
    )
    if not paths or not all(is_record_path(path, root) for path in paths):
        return False
    for path in paths:
        if PurePosixPath(path).name != "change.toml":
            continue
        before = committed_blob(repository, older, path)
        after = committed_blob(repository, newer, path)
        if before is None or after is None:
            return False
        try:
            if contract_digest(parse_change_record(before[1]).contract) != contract_digest(
                parse_change_record(after[1]).contract
            ):
                return False
        except ValueError:
            return False
    return True


def records_only_ancestors(repository: Path, root: str, base: str, tip: str) -> tuple[str, ...]:
    """First-parent ancestors after ``base`` that ``tip`` reaches by a records-only range.

    Nearest first; the walk stops at the first ancestor it cannot reach that way.
    """
    reached = []
    for commit in git_output(
        repository, "rev-list", "--first-parent", f"{base}..{tip}"
    ).splitlines()[1:]:
        if not records_only(repository, root, commit, tip):
            break
        reached.append(commit)
    return tuple(reached)


def written_packages(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str
) -> tuple[str, ...]:
    """Change packages whose record the member's own commits wrote and its base lacks.

    Only first-parent non-merge commits count, so a package that arrives through
    a synchronization merge is never the member's own, and one the member wrote
    stays its own after a batch synchronization brings back identical content.
    """
    root = changes_root(manifest)
    depth = len(PurePosixPath(root).parts)
    written: set[str] = set()
    for commit in git_output(
        repository, "rev-list", "--first-parent", "--no-merges", f"{base}..{tip}"
    ).splitlines():
        for path in git_output(
            repository, "diff-tree", "--no-commit-id", "--name-only", "-r", commit, "--", root
        ).splitlines():
            parts = PurePosixPath(path).parts
            if len(parts) == depth + 2 and parts[-1] == "change.toml":
                written.add(parts[depth])
    return tuple(
        sorted(
            change_id
            for change_id in written
            if committed_blob(repository, tip, f"{root}/{change_id}/change.toml") is not None
            and not git_output(
                repository, "ls-tree", "-d", "--name-only", base, "--", f"{root}/{change_id}"
            )
        )
    )


def member_scope(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str
) -> DeliveryScope:
    scope = delivery_scope(
        repository, manifest, base, tip, paths=member_contribution_paths(repository, base, tip)
    )
    held = {*scope.first_delivered, *(item.change_id for item in scope.previously_delivered)}
    written = tuple(
        change_id
        for change_id in written_packages(repository, manifest, base, tip)
        if change_id not in held
    )
    if not written:
        return scope
    return DeliveryScope(
        tuple(sorted((*scope.first_delivered, *written))), scope.previously_delivered
    )


def delivered_plans(
    repository: Path, manifest: RepositoryManifest, change_ids: tuple[str, ...], tip: str
) -> tuple[str, ...]:
    root = changes_root(manifest)
    result: list[str] = []
    for change_id in change_ids:
        read_package(repository, manifest, change_id, tip)
        result.append(f"{root}/{change_id}/change.toml")
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
class ConsolidatedPackage:
    record: ChangeRecord

    def require_approval(self) -> None:
        if self.record.status != "active" or self.record.approval is None:
            raise ChangeError(f"change {self.record.id} is not implementation-authorized")


def read_package(
    repository: Path, manifest: RepositoryManifest, change_id: str, revision: str
) -> ConsolidatedPackage:
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
            if competing_legacy_authorities(f"{root}/change.toml", frozenset(legacy.splitlines())):
                raise ValueError("change has competing consolidated and legacy authorities")
            record = parse_change_record(source[1])
            if record.id != change_id:
                raise ValueError("consolidated record declares another change identity")
            return ConsolidatedPackage(record)
        raise ValueError("approved change record is unavailable")
    except (GitError, ValueError, KeyError) as error:
        raise ChangeError(
            f"change {change_id} package is unavailable or invalid: {error}"
        ) from error


APPROVAL_ORDER_REMEDY = (
    "Commit implementation after the approval commit. Changes inside the approval "
    "commit do not count. Do not amend, rebase or otherwise rewrite history to "
    "reorder them; add a new commit instead."
)


@dataclass(frozen=True)
class ApprovalOrder:
    """Whether approved tip packages have valid own implementation coverage."""

    approval_commit: str | None
    implementation_commit: str | None

    @property
    def satisfied(self) -> bool:
        return self.implementation_commit is not None


def approval_order(
    repository: Path,
    manifest: RepositoryManifest,
    base: str,
    tip: str,
    change_ids: tuple[str, ...],
) -> ApprovalOrder:
    """Judge every own implementation at its parent and coverage of approved tip packages."""

    for change_id in change_ids:
        read_package(repository, manifest, change_id, tip).require_approval()
    commits = tuple(
        git_output(
            repository, "rev-list", "--reverse", "--first-parent", "--no-merges", f"{base}..{tip}"
        ).splitlines()
    )
    applications: frozenset[str] = frozenset()
    if change_ids and any(
        path.endswith("/events.jsonl")
        for path in git_output(repository, "diff", "--name-only", base, tip).splitlines()
    ):
        try:
            applications = decision_application_commits(repository, change_ids, commits, commit=tip)
        except DevelopmentReviewError as error:
            raise ChangeError(str(error)) from error
    covered: set[str] = set()
    implementation: str | None = None
    approval: str | None = None
    for commit in commits:
        action_manifest = _action_manifest(repository, manifest, commit)
        paths = git_output(
            repository, "diff-tree", "--no-commit-id", "--name-only", "-r", commit
        ).splitlines()
        if _is_implementation(
            paths,
            changes_root(action_manifest) + "/",
            action_manifest.repository.decisions.rstrip("/") + "/",
        ):
            require_member_commit(repository, action_manifest, base, commit)
        elif commit not in applications:
            continue
        # Accepted decision applications retain the authority-only implementation path.
        carried = carried_changes(repository, action_manifest, base, commit)
        required = {
            change_id: contract_digest(
                read_package(repository, action_manifest, change_id, commit).record.contract
            )
            for change_id in carried
        }
        parent = git_output(repository, "rev-parse", f"{commit}^")
        if not _approval_binds(repository, action_manifest, parent, required):
            raise ChangeError(
                f"implementation commit {commit} does not follow approval",
                expected=APPROVAL_FIRST_REMEDY,
            )
        covered.update(carried)
        approval = parent
        implementation = commit
    if not set(change_ids).issubset(covered):
        return ApprovalOrder(approval, None)
    return ApprovalOrder(approval, implementation)


def _approval_binds(
    repository: Path,
    manifest: RepositoryManifest,
    commit: str,
    required_contracts: dict[str, str],
) -> bool:
    """Whether ``commit`` holds an owner authorization for every required change."""
    try:
        for change_id in required_contracts:
            package = read_package(repository, manifest, change_id, commit)
            package.require_approval()
    except ChangeError:
        return False
    return True


def _action_manifest(
    repository: Path, manifest: RepositoryManifest, commit: str
) -> RepositoryManifest:
    """Use the action's path bindings even when later commits change those bindings.

    Attribution reads no validation configuration. Binding-only parsing also
    permits approval records preceding a validation-format migration.
    """
    bindings = parse_bindings(git_output(repository, "show", f"{commit}:signetum.toml"))
    return replace(
        manifest,
        repository=replace(
            manifest.repository,
            changes=bindings.repository.changes,
            decisions=bindings.repository.decisions,
        ),
    )


def _is_implementation(paths: list[str], root: str, decisions: str) -> bool:
    """A commit implements when it changes a path outside change records and decisions."""
    return any(not path.startswith((root, decisions)) for path in paths)


def require_member_changes(
    repository: Path,
    manifest: RepositoryManifest,
    base: str,
    tip: str,
) -> tuple[str, ...]:
    """Judge own implementation after approval in the package's one branch."""

    carried = carried_changes(repository, manifest, base, tip)
    if not git_output(repository, "rev-list", "--max-count=1", f"{base}..{tip}"):
        raise ChangeError("member has no own implementation commits")
    if not carried:
        raise ChangeError("member requires an approved change package")
    order = approval_order(repository, manifest, base, tip, carried)
    if order.satisfied:
        return carried
    raise ChangeError(
        "member is plan stage: each approved package needs an own implementation commit"
        + (f" {order.approval_commit}" if order.approval_commit else ""),
        expected=APPROVAL_ORDER_REMEDY,
    )


def carried_changes(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str
) -> tuple[str, ...]:
    """The approved change packages a member carries, each bound to the member's base."""

    scope = member_scope(repository, manifest, base, tip)
    carried = tuple(
        sorted(
            set(
                (
                    *scope.first_delivered,
                    *(
                        item.change_id
                        for item in scope.previously_delivered
                        if any(
                            committed_blob(
                                repository,
                                revision,
                                f"{changes_root(manifest)}/{item.change_id}/change.toml",
                            )
                            is not None
                            for revision in (base, tip)
                        )
                    ),
                )
            )
        )
    )
    for change_id in carried:
        package = read_package(repository, manifest, change_id, tip)
        package.require_approval()
        if package.record.contract.approved_base != base:
            raise ChangeError("consolidated approval does not match the registered workspace base")
    return carried


APPROVAL_FIRST_REMEDY = (
    "Commit the approval first: record the owner's actual approval in the change record "
    "and commit it on its own, then commit the implementation after it. A commit that "
    "carries the approval together with implementation does not count."
)


def require_member_commit(
    repository: Path, manifest: RepositoryManifest, base: str, commit: str
) -> None:
    """Judge one new member commit with the approval order ready applies to every commit.

    A commit that changes only change records and decisions always passes. Any
    other commit must follow, in its parent, the committed approval of each
    change package the member carries, binding the contract the commit holds.
    """

    manifest = _action_manifest(repository, manifest, commit)
    root = changes_root(manifest) + "/"
    decisions = manifest.repository.decisions.rstrip("/") + "/"
    paths = git_output(
        repository, "diff-tree", "--no-commit-id", "--name-only", "-r", commit
    ).splitlines()
    if not _is_implementation(paths, root, decisions):
        return
    try:
        carried = carried_changes(repository, manifest, base, commit)
        if not carried:
            raise ChangeError("member requires an approved change package")
        required = {
            change_id: contract_digest(
                read_package(repository, manifest, change_id, commit).record.contract
            )
            for change_id in carried
        }
    except ChangeError as error:
        raise ChangeError(
            f"implementation commit {commit} has no approved change package: {error}",
            expected=APPROVAL_FIRST_REMEDY,
        ) from error
    parent = git_output(repository, "rev-parse", f"{commit}^")
    if not _approval_binds(repository, manifest, parent, required):
        raise ChangeError(
            f"implementation commit {commit} does not follow a committed approval of "
            + ", ".join(sorted(required)),
            expected=APPROVAL_FIRST_REMEDY,
        )


@dataclass(frozen=True)
class Attribution:
    """A verdict derived from one commit and its parent authority."""

    commit: str
    authority: Literal["batch-authorization", "change"]
    changes: list[str]
    contract_digests: dict[str, str]


def commit_attribution(
    repository: Path, manifest: RepositoryManifest, record: WorkspaceRecord, commit: str
) -> Attribution | None:
    """Attribute one direct batch commit without consulting a later tip."""
    manifest = _action_manifest(repository, manifest, commit)
    parents = git_output(repository, "rev-list", "--parents", "-n", "1", commit).split()[1:]
    if len(parents) != 1:
        return None
    parent = parents[0]
    paths = git_output(
        repository, "diff-tree", "--no-commit-id", "--name-only", "-r", commit
    ).splitlines()
    if not paths:
        return None
    root = changes_root(manifest) + "/"
    decisions = manifest.repository.decisions.rstrip("/") + "/"
    implementation = _is_implementation(paths, root, decisions)
    if implementation and record.authorization is not None:
        return Attribution(commit, "batch-authorization", [], {})
    depth = len(PurePosixPath(root).parts)
    touched = sorted(
        {PurePosixPath(path).parts[depth] for path in paths if is_record_path(path, root)}
    )
    if not implementation:
        return Attribution(commit, "change", touched, {}) if touched else None
    approved: dict[str, str] = {}
    for change_id in written_packages(repository, manifest, record.base, parent):
        try:
            before = read_package(repository, manifest, change_id, parent)
            before.require_approval()
            current = read_package(repository, manifest, change_id, commit)
            digest = contract_digest(before.record.contract)
            current.require_approval()
            approved[change_id] = digest
        except ChangeError:
            continue
    if not approved:
        raise ChangeError(
            f"batch commit {commit} is not attributed to an approved batch-owned change",
            expected=(
                "Fix a member-owned defect in its member and admit the new ready tip. "
                "For this legacy batch, commit the batch-owned approval first, then the fix. "
                "New batches record combination-repair authorization at batch-open."
            ),
        )
    return Attribution(commit, "change", sorted(approved), approved)


def batch_owned_commits(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str
) -> list[dict[str, object]]:
    """Recompute action-time verdicts for direct commits in the batch history."""
    record = read_record(state_root(repository), branch_name(repository))
    return [
        asdict(attribution)
        for commit in git_output(
            repository, "rev-list", "--reverse", "--first-parent", "--no-merges", f"{base}..{tip}"
        ).splitlines()
        if (attribution := commit_attribution(repository, manifest, record, commit)) is not None
    ]
