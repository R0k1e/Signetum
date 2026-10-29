# Generated from signetum.protocol_cli; edit the engine source and regenerate.
"""Local authoring and journal utilities; lifecycle operations remain separate."""

import sys

from . import (
    change_open,
    change_record,
    ci_partitions,
    development_store,
    migration,
    pytest_scheduling,
    python_selection,
    test_diagnostic,
)
from .existing_runner import main as runner_main
from .operation_cli import OperationParser, utility_failure

JOURNAL_OPERATIONS = (
    "current",
    "status",
    "history",
    "record",
    "resolve",
    "retract",
    "reconcile",
    "retire",
)


def main(arguments: list[str] | None = None) -> int:
    supplied = sys.argv[1:] if arguments is None else arguments
    parser = OperationParser(
        description="Daily: change-open, view, status, current, record, resolve, test.",
        epilog=(
            "History: history. Conditional decision/repair: reconcile, retract, retire. "
            "Adoption: migration, runner. "
            "Optional optimization: select-python, schedule, partition. "
            "Use <command> --help for that operation; lifecycle commands remain separate."
        ),
    )
    parser.add_argument(
        "command",
        metavar="<command>",
        choices=[
            "change-open",
            "view",
            "migration",
            "runner",
            "test",
            "select-python",
            "partition",
            "schedule",
            *JOURNAL_OPERATIONS,
        ],
    )
    try:
        parsed = parser.parse_args(supplied[:1])
        remaining = supplied[1:]
        if parsed.command == "change-open":
            return change_open.main(remaining)
        if parsed.command == "view":
            return change_record.main([*remaining, "--review"])
        if parsed.command == "test":
            return test_diagnostic.main(remaining)
        if parsed.command == "select-python":
            return python_selection.main(remaining)
        if parsed.command == "schedule":
            return pytest_scheduling.main(remaining)
        if parsed.command == "partition":
            return ci_partitions.main(remaining)
        if parsed.command == "runner":
            return runner_main(remaining)
        if parsed.command == "migration":
            return migration.main(remaining)
        return development_store.main([parsed.command, *remaining])
    except (ValueError, OSError) as error:
        return utility_failure(supplied[0] if supplied else "protocol", error)


if __name__ == "__main__":
    raise SystemExit(main())
