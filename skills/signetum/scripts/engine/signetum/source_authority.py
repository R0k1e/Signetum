"""One committed-source and repository-path boundary for development authorities."""

import re
import tomllib
from pathlib import Path, PurePosixPath

from signetum.change.models import (
    Decision,
    DecisionStatus,
    complete_decision_replacements,
    require_relative_path,
)
from signetum.change.paths import changes_root
from signetum.git import git_output, run_git
from signetum.manifest import load_manifest, parse_manifest
from signetum.traceability.loading import parse_decision


def authority_roots(
    repository: Path, *, commit: str | None = None, historical: bool = False
) -> tuple[str, str]:
    path = repository / "signetum.toml"
    if commit is None:
        if not path.exists():
            return "changes", "docs/decisions"
        manifest = load_manifest(path)
    else:
        source = committed_blob(repository, commit, "signetum.toml")
        if source is None:
            return "changes", "docs/decisions"
        if historical:
            archived = tomllib.loads(source[1])
            version = archived.get("schema_version")
            if type(version) is int and version in {2, 3, 4, 5}:
                # An approval location is immutable; old executable settings
                # are neither reinterpreted nor accepted for current writes.
                bindings = archived["repository"]
                if version == 2:
                    pattern = PurePosixPath(bindings["specifications"])
                    if pattern.parts[-3:] != ("*", "specs", "*.toml"):
                        raise ValueError("historical change binding has no exact package root")
                    raw_root = PurePosixPath(*pattern.parts[:-3]).as_posix()
                else:
                    raw_root = bindings["changes"]
                root = str(require_relative_path(raw_root))
                if any(character in root for character in "*?[]"):
                    raise ValueError("historical change binding has no exact package root")
                decisions = str(require_relative_path(bindings["decisions"]))
                return root, decisions
        manifest = parse_manifest(source[1])
    return changes_root(manifest), manifest.repository.decisions


def source_path(repository: Path, relative: str) -> Path:
    parts = require_relative_path(relative).parts
    result = repository.resolve()
    for part in parts:
        result /= part
        if result.is_symlink():
            raise ValueError(f"journal authority cannot traverse a symlink: {relative}")
    if not result.resolve().is_relative_to(repository.resolve()):
        raise ValueError("journal path escapes the repository")
    return result


def require_committed_bindings(repository: Path, commit: str) -> None:
    relative = "signetum.toml"
    path = source_path(repository, relative)
    present = committed_blob_identity(repository, commit, relative) is not None
    if path.exists() != present or (present and not path.is_file()):
        raise ValueError("repository authority bindings must match the committed source")
    result = run_git(
        repository, "diff", "--quiet", "--no-ext-diff", "--no-textconv", commit, "--", relative
    )
    if result.returncode:
        raise ValueError("repository authority bindings must match the committed source")


def committed_blob_identity(repository: Path, commit: str, relative: str) -> str | None:
    require_relative_path(relative)
    entries = git_output(repository, "ls-tree", "-z", commit, "--", relative, strip=False)
    if not entries:
        return None
    if entries.count("\0") != 1:
        raise ValueError("authority does not name one regular committed file")
    header, separator, name = entries.rstrip("\0").partition("\t")
    mode, kind, identity = header.split()
    if not separator or name != relative or kind != "blob" or mode not in {"100644", "100755"}:
        raise ValueError("authority is not a regular committed file")
    return identity


def committed_blob(repository: Path, commit: str, relative: str) -> tuple[str, str] | None:
    identity = committed_blob_identity(repository, commit, relative)
    if identity is None:
        return None
    return identity, git_output(repository, "cat-file", "blob", identity, strip=False)


def require_ancestor(repository: Path, older: str, newer: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", older) is None:
        raise ValueError("journal authority requires an exact approved commit identity")
    result = run_git(repository, "merge-base", "--is-ancestor", older, newer)
    if result.returncode:
        raise ValueError("journal approval is outside the accepted commit ancestry")


def require_accepted_decision(
    repository: Path,
    commit: str,
    relative: str,
    decision_root: str,
) -> Decision:
    path = require_relative_path(relative)
    root = require_relative_path(decision_root)
    if not path.is_relative_to(root) or path.suffix != ".md":
        raise ValueError("decision acceptance must be a standalone declared authority")
    blob = committed_blob(repository, commit, relative)
    if blob is None:
        raise ValueError("standalone decision approval is not committed")
    decision = parse_decision(blob[1], relative)
    if decision.status != DecisionStatus.ACCEPTED:
        raise ValueError("standalone decision authority is not currently accepted")
    successors = {}
    if decision.superseded_by:
        paths = git_output(
            repository, "ls-tree", "-r", "--name-only", "-z", commit, "--", decision_root
        )
        candidates = tuple(
            PurePosixPath(item) for item in paths.split("\0") if item.endswith(".md")
        )
        for reference in decision.superseded_by:
            target = require_relative_path(reference)
            if target.suffix != ".md":
                continue
            options = (
                [target]
                if target.is_relative_to(root)
                else [root / target]
                if len(target.parts) > 1
                else [item for item in candidates if item.name == target.name]
            )
            if len(options) > 1:
                raise ValueError("successor decision identity is ambiguous")
            if options:
                replacement = committed_blob(repository, commit, options[0].as_posix())
                if replacement is not None:
                    obtained = parse_decision(replacement[1], options[0].as_posix())
                    successors[obtained.name] = obtained
    if complete_decision_replacements(decision, successors):
        raise ValueError("standalone decision authority is fully superseded")
    return decision
