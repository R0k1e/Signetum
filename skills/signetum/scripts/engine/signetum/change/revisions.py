"""Derive contract revisions and diagnostics from committed change records."""

from pathlib import Path

from signetum.change_record import ChangeRecord, contract_digest, parse_change_record
from signetum.git import GitError, git_output
from signetum.operations import AdmissionError
from signetum.serialization import contract_mapping
from signetum.source_authority import committed_blob


def _record_commits(repository: Path, path: str, tip: str, *, reverse: bool = False) -> list[str]:
    order = ("--reverse",) if reverse else ()
    return git_output(
        repository,
        "log",
        "--full-history",
        "--simplify-merges",
        "--topo-order",
        *order,
        "--format=%H",
        tip,
        "--",
        f":(literal){path}",
    ).splitlines()


def _record_at(repository: Path, path: str, commit: str) -> ChangeRecord | None:
    blob = committed_blob(repository, commit, path)
    return parse_change_record(blob[1]) if blob is not None else None


def has_approved_revision(repository: Path, path: str, tip: str) -> bool:
    """Whether the tip or an earlier record on its ancestry parses with approval."""

    def approved(commit: str) -> bool:
        try:
            record = _record_at(repository, path, commit)
        except GitError:
            raise
        except ValueError:
            return False
        return record is not None and record.approval is not None

    return approved(tip) or any(
        approved(commit) for commit in _record_commits(repository, path, tip) if commit != tip
    )


def authorization_history(repository: Path, path: str, tip: str) -> dict[str, object]:
    # Look at the actual tip independently of Git's path-history ordering.
    try:
        current = _record_at(repository, path, tip)
    except GitError:
        raise
    except ValueError as error:
        raise AdmissionError(f"invalid current change record {path}: {error}") from error
    if current is None:
        raise AdmissionError(f"current change record is missing: {path}")

    approval_commit = None
    previous = None
    revisions = []
    invalid_drafts = []
    superseded_invalid = []
    for commit in _record_commits(repository, path, tip, reverse=True):
        try:
            record = current if commit == tip else _record_at(repository, path, commit)
        except GitError:
            raise
        except ValueError as error:
            diagnostics = invalid_drafts if approval_commit is None else superseded_invalid
            diagnostics.append({"commit": commit, "cause": str(error)})
            continue
        if record is None:
            continue
        if approval_commit is None:
            if record.approval is None:
                continue
            approval_commit = commit
        elif previous is not None and previous != record.contract:
            before, after = contract_mapping(previous), contract_mapping(record.contract)
            revisions.append(
                {
                    "commit": commit,
                    "before": contract_digest(previous),
                    "after": contract_digest(record.contract),
                    "fields": {
                        key: {"before": before[key], "after": after[key]}
                        for key in before
                        if before[key] != after[key]
                    },
                }
            )
        previous = record.contract
    return {
        "approval_commit": approval_commit,
        "contract_revisions": revisions,
        "invalid_drafts": invalid_drafts,
        "superseded_invalid": superseded_invalid,
    }
