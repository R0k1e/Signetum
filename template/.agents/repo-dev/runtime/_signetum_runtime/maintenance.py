# Generated from signetum.maintenance; edit the engine source and regenerate.
"""Explicit local maintenance, separate from the eight lifecycle operations."""

import argparse
import sys
from pathlib import Path

from .operation_cli import OperationParser, run_operation
from .workspace_operations import batch_discard, cleanup, workspace_sync, worktree_prepare
from .workspaces import state_root


def _parser() -> argparse.ArgumentParser:
    parser = OperationParser(prog="maintenance")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("workspace-sync")
    sync.add_argument("--batch", type=Path)
    prepare = commands.add_parser("worktree-prepare")
    prepare.add_argument("worktree", type=Path)
    clean = commands.add_parser("cleanup")
    clean.add_argument("--worktree", type=Path)
    clean.add_argument("--branch")
    clean.add_argument("--all-delivered", action="store_true")
    clean.add_argument("--protected-worktree", type=Path, action="append", default=[])
    clean.add_argument("--discard", action="store_true")
    discard = commands.add_parser("batch-discard")
    discard.add_argument("batch", type=Path)
    return parser


def _dispatch(repository: Path, supplied: list[str]) -> dict[str, object]:
    parsed = _parser().parse_args(supplied)
    result: dict[str, object]
    if parsed.command == "workspace-sync":
        result = workspace_sync(repository, parsed.batch.resolve() if parsed.batch else None)
    elif parsed.command == "worktree-prepare":
        result = dict(worktree_prepare(parsed.worktree.resolve()))
    elif parsed.command == "cleanup":
        result = cleanup(
            repository,
            worktree=parsed.worktree,
            branch=parsed.branch,
            all_delivered=parsed.all_delivered,
            discard=parsed.discard,
            protected_worktrees=tuple(parsed.protected_worktree),
        )
    elif parsed.command == "batch-discard":
        result = batch_discard(parsed.batch.resolve())
    return result


def main(arguments: list[str] | None = None) -> int:
    supplied = sys.argv[1:] if arguments is None else arguments
    operation = supplied[0] if supplied else "maintenance"
    repository = Path.cwd().resolve()
    return run_operation(
        repository, operation, lambda: _dispatch(repository, supplied), state_root=state_root
    )


if __name__ == "__main__":
    raise SystemExit(main())
