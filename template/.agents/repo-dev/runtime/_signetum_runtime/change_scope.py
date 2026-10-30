# Generated from signetum.change.scope; edit the engine source and regenerate.
"""Change ownership derived from committed paths, never from commit prose."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .change_paths import changes_root
from .change_record import (
    ChangeRecord,
    competing_legacy_authorities,
    contract_digest,
    parse_change_record,
)
from .decision_identity import numbered_targets
from .development_store import DevelopmentReviewError, decision_application_commits
from .git import GitError, git_output, run_git
from .manifest import RepositoryManifest
from .operations import OperationError
from .source_authority import committed_blob
from .synchronization import member_contribution_paths


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


def require_member_changes(
    repository: Path,
    manifest: RepositoryManifest,
    base: str,
    tip: str,
) -> tuple[str, ...]:
    """Judge own implementation after approval in the package's one branch."""

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
    applications: frozenset[str] = frozenset()
    if required_contracts and any(
        path.endswith("/events.jsonl")
        for path in git_output(repository, "diff", "--name-only", base, tip).splitlines()
    ):
        try:
            applications = decision_application_commits(
                repository, tuple(required_contracts), commits, commit=tip
            )
        except DevelopmentReviewError as error:
            raise ChangeError(str(error)) from error
    approved = False
    for commit in (base, *commits):
        if approved:
            paths = git_output(
                repository, "diff-tree", "--no-commit-id", "--name-only", "-r", commit
            ).splitlines()
            if commit in applications or any(
                not path.startswith((root, decisions)) for path in paths
            ):
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
