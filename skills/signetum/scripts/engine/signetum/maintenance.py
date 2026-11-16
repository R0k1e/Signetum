"""Explicit local maintenance, separate from the seven lifecycle operations."""

import argparse
import json
import sys
from pathlib import Path

from signetum.commit_check import main as commit_check
from signetum.lifecycle import sync_batch
from signetum.operation_cli import OperationParser, run_operation
from signetum.operation_records import (
    adopt_legacy_history,
    adopt_repository_engine,
    export_operations,
    import_operations,
    read_message_file,
    record_decision_mapping,
)
from signetum.operations import AdmissionError
from signetum.workspace_operations import (
    branch_abandon,
    cleanup,
    leftovers,
    workspace_abandon,
    workspace_sync,
    worktree_prepare,
)
from signetum.workspaces import branch_name, primary_worktree, read_record, state_root


def _parser() -> argparse.ArgumentParser:
    parser = OperationParser(prog="maintenance")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("commit-check")
    sync = commands.add_parser("workspace-sync")
    sync.add_argument("--batch", type=Path)
    sync.add_argument(
        "--message-file",
        type=Path,
        required=True,
        help="Commit message file for the synchronization commit.",
    )
    exported = commands.add_parser("operation-export")
    exported.add_argument("--from", dest="start", required=True, help="Range start commit.")
    exported.add_argument("--to", dest="end", required=True, help="Range end commit.")
    exported.add_argument("--output", type=Path, required=True, help="Portable proof file.")
    imported = commands.add_parser("operation-import")
    imported.add_argument("--input", type=Path, required=True, help="Portable proof file.")
    adopted = commands.add_parser(
        "adopt-legacy",
        description=(
            "Adopt explicit commits as retained legacy history. This does not move an "
            "existing cutover forward and does not trust a copied trailer."
        ),
    )
    adopted.add_argument(
        "--commit",
        action="append",
        required=True,
        help="Commit already on a local branch whose older history is genuine legacy proof.",
    )
    mapping = commands.add_parser(
        "record-decision-mapping",
        description=(
            "Record a human numbering commit and the approved change basis it binds. "
            "The message file must match that commit. This creates no new commit."
        ),
    )
    mapping.add_argument("--commit", required=True, help="Existing numbering commit.")
    mapping.add_argument("--base", required=True, help="Approved change basis commit.")
    mapping.add_argument("--directory", required=True, help="Decision directory the rename is in.")
    mapping.add_argument("--message-file", type=Path, required=True)
    handoff = commands.add_parser(
        "adopt-repository-engine",
        description=(
            "Copy this repository engine and the declared preparation inputs it needs "
            "onto a repository-pinned batch. A completed handoff for the same source "
            "and message is reused. The batch pin stays repository."
        ),
    )
    handoff.add_argument("--message-file", type=Path, required=True)
    handoff.add_argument(
        "--source",
        help="Ready commit whose repository engine and declared preparation inputs are adopted.",
    )
    prepare = commands.add_parser("worktree-prepare")
    prepare.add_argument("worktree", type=Path)
    clean = commands.add_parser("cleanup")
    clean.add_argument("--worktree", type=Path)
    clean.add_argument("--branch", help="Workspace branch or loose change/* or batch/* branch.")
    clean.add_argument(
        "--all-delivered",
        action="store_true",
        help="Sweep proven workspaces and loose Signetum branches; Git may refuse branch deletion.",
    )
    clean.add_argument("--protected-worktree", type=Path, action="append", default=[])
    clean.add_argument("--discard", action="store_true")
    abandon = commands.add_parser(
        "workspace-abandon",
        description=(
            "Remove a workspace that is neither delivered nor contained, only with the "
            "owner's actual confirmation of its exact tip. An Agent may run it, naming the "
            "owner in --actor and citing in --source where the owner confirmed that tip, "
            "such as the conversation; never infer a confirmation. The repository is the "
            "named workspace's own."
        ),
    )
    abandon.add_argument("worktree", type=Path, help="Existing workspace directory.")
    abandon.add_argument("expected_tip", help="Full commit the owner confirmed abandoning.")
    abandon.add_argument("--actor", required=True, help="Owner who confirmed abandonment.")
    abandon.add_argument(
        "--source", required=True, help="Where the owner confirmed it, such as the conversation."
    )
    abandon.add_argument("--reason", required=True, help="Why the work is abandoned.")
    abandon.add_argument("--discard", action="store_true")
    commands.add_parser(
        "leftovers",
        description=(
            "List checkouts without a workspace record and local branches without a checkout "
            "that the delivery branch does not contain, each with its removal command."
        ),
    )
    branch = commands.add_parser(
        "branch-abandon",
        description=(
            "Delete a local branch without a checkout only with the owner's actual "
            "confirmation of its exact tip; a retirement record keeps the tip. An Agent may "
            "run it, naming the owner in --actor and citing in --source where the owner "
            "confirmed that tip; never infer a confirmation."
        ),
    )
    branch.add_argument("branch", help="Local branch name.")
    branch.add_argument("expected_tip", help="Full commit the owner confirmed abandoning.")
    branch.add_argument("--actor", required=True, help="Owner who confirmed abandonment.")
    branch.add_argument(
        "--source", required=True, help="Where the owner confirmed it, such as the conversation."
    )
    branch.add_argument("--reason", required=True, help="Why the work is abandoned.")
    return parser


def _dispatch(repository: Path, supplied: list[str]) -> dict[str, object]:
    parsed = _parser().parse_args(supplied)
    result: dict[str, object]
    if parsed.command == "workspace-sync":
        source = parsed.batch.resolve() if parsed.batch else None
        message = read_message_file(parsed.message_file)
        if read_record(state_root(repository), branch_name(repository)).kind == "batch":
            result = sync_batch(repository, source, message=message)
        else:
            result = workspace_sync(repository, source, message=message)
    elif parsed.command == "operation-export":
        document = export_operations(repository, parsed.start, parsed.end)
        _write_export(parsed.output, document)
        operations = document["operations"]
        qualifications = document["qualifications"]
        if not isinstance(operations, list) or not isinstance(qualifications, list):
            raise AdmissionError("operation export is invalid")
        result = {
            "status": "exported",
            "operations": len(operations),
            "qualifications": len(qualifications),
        }
    elif parsed.command == "operation-import":
        result = import_operations(repository, _read_export(parsed.input))
    elif parsed.command == "adopt-legacy":
        adopted_history = adopt_legacy_history(repository, parsed.commit)
        result = {"status": "adopted", "tips": adopted_history.get("tips")}
    elif parsed.command == "record-decision-mapping":
        result = record_decision_mapping(
            repository,
            parsed.commit,
            parsed.base,
            parsed.directory,
            read_message_file(parsed.message_file),
        )
    elif parsed.command == "adopt-repository-engine":
        result = adopt_repository_engine(
            repository,
            read_message_file(parsed.message_file),
            parsed.source,
        )
    elif parsed.command == "worktree-prepare":
        result = dict(worktree_prepare(parsed.worktree.resolve()))
    elif parsed.command == "cleanup":
        result = cleanup(
            _named_repository(parsed.worktree, repository),
            worktree=parsed.worktree,
            branch=parsed.branch,
            all_delivered=parsed.all_delivered,
            discard=parsed.discard,
            protected_worktrees=tuple(parsed.protected_worktree),
        )
    elif parsed.command == "workspace-abandon":
        result = workspace_abandon(
            _named_repository(parsed.worktree, repository),
            parsed.worktree,
            parsed.expected_tip,
            actor=parsed.actor,
            source=parsed.source,
            reason=parsed.reason,
            discard=parsed.discard,
        )
    elif parsed.command == "leftovers":
        result = leftovers(repository)
    elif parsed.command == "branch-abandon":
        result = branch_abandon(
            repository,
            parsed.branch,
            parsed.expected_tip,
            actor=parsed.actor,
            source=parsed.source,
            reason=parsed.reason,
        )
    return result


def _write_export(path: Path, document: dict[str, object]) -> None:
    try:
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as error:
        raise AdmissionError(f"operation export is unwritable: {path.name}") from error


def _read_export(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise AdmissionError(f"operation export is missing: {path.name}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise AdmissionError(f"operation export is unreadable: {path.name}") from error
    if not isinstance(document, dict):
        raise AdmissionError("operation export is invalid")
    return document


def _named_repository(worktree: Path | None, caller: Path) -> Path:
    """An operation on a named workspace acts on that workspace's repository.

    Its primary checkout holds the delivery binding and runs no removed workspace.
    """
    if worktree is None:
        return caller
    if not worktree.is_dir():
        raise AdmissionError(
            f"workspace must be an existing worktree directory; a branch name is not a path: "
            f"{worktree}"
        )
    return primary_worktree(worktree.resolve())


def main(arguments: list[str] | None = None) -> int:
    supplied = sys.argv[1:] if arguments is None else arguments
    if supplied == ["commit-check"]:
        return commit_check()
    operation = supplied[0] if supplied else "maintenance"
    repository = Path.cwd().resolve()
    return run_operation(
        repository, operation, lambda: _dispatch(repository, supplied), state_root=state_root
    )


if __name__ == "__main__":
    raise SystemExit(main())
