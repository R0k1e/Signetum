# Generated from signetum.protocol_cli; edit the engine source and regenerate.
"""Local authoring and journal utilities; lifecycle operations remain separate."""

import argparse
import sys

from . import change_open, change_record, development_store, migration
from .existing_runner import main as runner_main

JOURNAL_OPERATIONS = (
    "current",
    "status-all",
    "history",
    "record",
    "resolve",
    "retract",
    "reconcile",
    "retire",
)


def main(arguments: list[str] | None = None) -> int:
    supplied = sys.argv[1:] if arguments is None else arguments
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["change-open", "view", "migration", "runner", *JOURNAL_OPERATIONS]
    )
    parsed = parser.parse_args(supplied[:1])
    remaining = supplied[1:]
    if parsed.command == "change-open":
        return change_open.main(remaining)
    if parsed.command == "view":
        return change_record.main([*remaining, "--review"])
    if parsed.command == "runner":
        return runner_main(remaining)
    if parsed.command == "migration":
        return migration.main(remaining)
    return development_store.main([parsed.command, *remaining])


if __name__ == "__main__":
    raise SystemExit(main())
