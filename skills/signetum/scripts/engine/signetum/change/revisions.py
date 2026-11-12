"""Derive contract revisions from the first valid authorization onward.

A change.toml that does not parse before that authorization is kept as a draft
diagnostic and is not authority. One that does not parse afterward still fails.
"""

from pathlib import Path

from signetum.change_record import contract_digest, parse_change_record
from signetum.git import git_output, run_git
from signetum.serialization import contract_mapping


def authorization_history(repository: Path, path: str, tip: str) -> dict[str, object]:
    approval_commit = None
    previous = None
    revisions = []
    invalid_drafts = []
    for commit in git_output(
        repository, "log", "--reverse", "--topo-order", "--format=%H", tip, "--", path
    ).splitlines():
        shown = run_git(repository, "show", f"{commit}:{path}")
        if shown.returncode:
            continue
        try:
            record = parse_change_record(shown.stdout)
        except ValueError as error:
            # Only drafts before a parsed approval are diagnostic. Later records stay strict.
            if approval_commit is not None:
                raise
            invalid_drafts.append({"commit": commit, "cause": str(error)})
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
    }
