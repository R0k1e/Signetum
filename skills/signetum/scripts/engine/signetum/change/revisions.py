"""Derive contract revisions from source history after the first authorization."""

from pathlib import Path

from signetum.change_record import contract_digest, parse_change_record
from signetum.git import git_output, run_git
from signetum.serialization import contract_mapping


def authorization_history(repository: Path, path: str, tip: str) -> dict[str, object]:
    approval_commit = None
    previous = None
    revisions = []
    for commit in git_output(
        repository, "log", "--reverse", "--topo-order", "--format=%H", tip, "--", path
    ).splitlines():
        shown = run_git(repository, "show", f"{commit}:{path}")
        if shown.returncode:
            continue
        record = parse_change_record(shown.stdout)
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
    return {"approval_commit": approval_commit, "contract_revisions": revisions}
