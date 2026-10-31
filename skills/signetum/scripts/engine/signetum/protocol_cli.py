"""Local authoring and journal utilities; lifecycle operations remain separate."""

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path

from signetum.change_record import contract_digest, parse_change_record
from signetum.development_log import (
    DevelopmentTransaction,
    transaction_identities,
)
from signetum.development_store import (
    append_transaction,
    approved_authority,
    judge_sources,
    parse_request,
    read_sources,
)
from signetum.git import git_output
from signetum.operation_cli import OperationParser, utility_failure
from signetum.profiles.existing_runner import main as runner_main
from signetum.serialization import contract_mapping, load_json
from signetum.source_authority import (
    authority_roots,
    committed_blob,
)
from signetum.workflow_status import workflow_status
from signetum.workspaces import read_record, state_root


def _semantic_request(
    repository: Path, options: argparse.Namespace
) -> tuple[DevelopmentTransaction, str]:
    """Bind semantic input once; the existing writer still judges every append."""
    branch = git_output(repository, "branch", "--show-current")
    workspace = read_record(state_root(repository), branch)
    if workspace.kind != "member":
        raise ValueError("journal requires a registered member workspace")
    commit = git_output(repository, "rev-parse", "HEAD")
    if options.change:
        change = options.change
    else:
        root, _ = authority_roots(repository, commit=commit)
        candidates = []
        for name in git_output(
            repository, "ls-tree", "-r", "--name-only", "-z", commit, "--", root
        ).split("\0"):
            if not name.endswith("/change.toml"):
                continue
            source = committed_blob(repository, commit, name)
            if source is None:
                continue
            record = parse_change_record(source[1])
            if (
                record.status == "active"
                and record.approval is not None
                and record.contract.approved_base == workspace.base
            ):
                candidates.append(record.id)
        if len(candidates) != 1:
            raise ValueError("cannot infer one approved change; name --change explicitly")
        change = candidates[0]
    record, _ = approved_authority(repository, change, commit)
    sources = read_sources(repository)
    if not options.id or not options.reason:
        raise ValueError("semantic writes require --id and --reason")
    identity = options.id if options.id.startswith(change + "/") else change + "/" + options.id
    body = {
        "id": identity,
        "change_id": change,
        "approval_digest": contract_digest(record.contract),
        "operation": options.operation,
        "reason": options.reason,
    }
    if options.operation != "resolve" and options.disposition != "resolved":
        raise ValueError("only resolve accepts --disposition")
    if options.operation == "record":
        if (
            not options.summary
            or not options.requirement
            or any((options.target, options.resolution, options.followup, options.accept_decisions))
        ):
            raise ValueError(
                "record requires --summary and --requirement, without resolution inputs"
            )
        body["observations"] = [
            {
                "id": identity + "/observation",
                "requirements": options.requirement,
                "summary": options.summary,
                "reason": options.reason,
                "evidence": options.evidence,
            }
        ]
    elif options.operation == "resolve":
        if not options.target or any(
            (options.summary, options.requirement, options.resolution, options.accept_decisions)
        ):
            raise ValueError("resolve requires --target, without observation or decision inputs")
        body["resolutions"] = [
            {
                "id": identity + "/resolution",
                "target": options.target,
                "status": options.disposition,
                "reason": options.reason,
                "evidence": options.evidence,
                "followup": options.followup,
            }
        ]
    elif options.operation == "retract":
        if (
            not options.target
            or not options.resolution
            or any(
                (
                    options.summary,
                    options.requirement,
                    options.evidence,
                    options.followup,
                    options.accept_decisions,
                )
            )
        ):
            raise ValueError("retract requires --target and --resolution only")
        body["retractions"] = [
            {
                "id": identity + "/retraction",
                "target": options.target,
                "resolution_id": options.resolution,
                "reason": options.reason,
            }
        ]
    elif options.operation == "reconcile" and options.accept_decisions:
        if any(
            (
                options.target,
                options.resolution,
                options.summary,
                options.requirement,
                options.evidence,
                options.followup,
            )
        ):
            raise ValueError("accepted-decision application does not accept observation inputs")
        observed = sources
        previous = next(
            (entry.transaction for entry in observed.entries if entry.transaction.id == identity),
            None,
        )
        if previous is not None:
            selected = previous.decisions
        else:
            applied = {
                decision.id: decision
                for entry in observed.entries
                for decision in entry.transaction.decisions
            }
            selected = tuple(
                decision for decision in record.contract.decisions if decision.id not in applied
            )
            if any(
                decision.id in applied and applied[decision.id] != decision
                for decision in record.contract.decisions
            ):
                raise ValueError("an accepted decision identity has changed content")
            if not selected:
                raise ValueError(
                    "No unapplied approved decisions; inspect current "
                    "or retry the original transaction ID."
                )
        body["decisions"] = [contract_mapping(item) for item in selected]

    else:
        raise ValueError("this operation needs its structured request")
    return parse_request(body), options.expected_history or sources.history_digest


def journal_main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=[
            "record",
            "resolve",
            "retract",
            "reconcile",
            "retire",
            "status",
            "current",
            "history",
        ],
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--request", type=Path)
    parser.add_argument("--expected-history")
    parser.add_argument("--change")
    parser.add_argument("--event")
    parser.add_argument("--id")
    parser.add_argument("--summary")
    parser.add_argument("--reason")
    parser.add_argument("--requirement", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--target")
    parser.add_argument(
        "--disposition", choices=["resolved", "rejected", "deferred"], default="resolved"
    )
    parser.add_argument("--followup")
    parser.add_argument("--resolution")
    parser.add_argument("--accept-decisions", action="store_true")
    sources = None
    try:
        options = parser.parse_args(arguments)
        if options.operation in {"status", "current", "history"}:
            if (
                any(
                    (
                        options.request,
                        options.expected_history,
                        options.id,
                        options.summary,
                        options.reason,
                        options.requirement,
                        options.evidence,
                        options.target,
                        options.followup,
                        options.resolution,
                        options.accept_decisions,
                    )
                )
                or options.disposition != "resolved"
            ):
                raise ValueError("read-only views do not accept mutation inputs")
            sources = read_sources(options.repository)
            if options.operation == "history":
                if bool(options.change) == bool(options.event):
                    raise ValueError("history requires exactly one change or event identity")
                selected = [
                    entry
                    for entry in sources.entries
                    if (options.change and entry.transaction.change_id == options.change)
                    or (
                        options.event and options.event in transaction_identities(entry.transaction)
                    )
                ]
                if not selected:
                    raise ValueError("no retained development event matches the history identity")
                payload: dict[str, object] = {
                    "schema_version": 1,
                    "status": "passed",
                    "history_digest": sources.history_digest,
                    "authority_coverage": "journal_only",
                    "entries": [contract_mapping(item) for item in selected],
                }
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                return 0
            result = judge_sources(options.repository, sources)
        else:
            if options.event is not None:
                raise ValueError("mutation commands do not accept event filters")
            if options.request is not None:
                if (
                    any(
                        (
                            options.change,
                            options.id,
                            options.summary,
                            options.reason,
                            options.requirement,
                            options.evidence,
                            options.target,
                            options.followup,
                            options.resolution,
                            options.accept_decisions,
                        )
                    )
                    or options.disposition != "resolved"
                ):
                    raise ValueError("structured requests cannot mix with semantic fields")
                if options.expected_history is None:
                    raise ValueError("structured requests require expected history identity")
                transaction = parse_request(load_json(options.request.read_text()))
                expected = options.expected_history
            else:
                transaction, expected = _semantic_request(options.repository, options)
            if transaction.operation != options.operation:
                raise ValueError("request operation differs from the selected command")
            result = append_transaction(options.repository, transaction, expected_history=expected)
        if options.operation in {"current", "status"} and (
            options.change is not None or options.event is not None
        ):
            raise ValueError("history filters require the history command")
        payload = {
            "schema_version": 1,
            "status": "passed",
            "history_digest": result.history_digest,
            "authority_coverage": "journal_only",
        }
        if options.operation == "current":
            payload["working_set"] = contract_mapping(result.working_set)
            payload["historical_authorities"] = {
                "directory": authority_roots(options.repository)[1],
                "mode": "read_on_demand",
            }
            payload["guidance"] = (
                "Current clauses do not replace historical sources without an accepted migration; "
                "consult relevant sources, not the whole log."
            )
        elif options.operation == "status":
            payload.update(
                workflow_status(
                    options.repository,
                    result,
                    source=sources.head
                    if sources is not None
                    else git_output(options.repository, "rev-parse", "HEAD"),
                )
            )
        else:
            affected = {item.id for item in transaction.observations}
            affected.update(item.target for item in transaction.resolutions)
            affected.update(item.target for item in transaction.retractions)
            affected.update(item.target for item in transaction.retirements)
            payload["applied_transaction"] = transaction.id
            payload["decision_transactions"] = [item.id for item in transaction.decisions]
            payload["observations"] = [
                contract_mapping(item)
                for item in result.observations
                if item.observation.id in affected
            ]
    except (OSError, ValueError, TypeError) as error:
        extra = {"history_digest": sources.history_digest} if sources is not None else {}
        return utility_failure((arguments or sys.argv[1:] or ["journal"])[0], error, **extra)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


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
            "Adoption: runner. "
            "Optional optimization: schedule, partition. "
            "Use <command> --help for that operation; lifecycle commands remain separate."
        ),
    )
    parser.add_argument(
        "command",
        metavar="<command>",
        choices=[
            "change-open",
            "view",
            "runner",
            "test",
            "partition",
            "schedule",
            *JOURNAL_OPERATIONS,
        ],
    )
    try:
        parsed = parser.parse_args(supplied[:1])
        remaining = supplied[1:]
        if parsed.command == "change-open":
            return import_module(f"{__package__}.change_open").main(remaining)
        if parsed.command == "view":
            return import_module(f"{__package__}.change_record").main([*remaining, "--review"])
        if parsed.command == "test":
            return import_module(f"{__package__}.test_diagnostic").main(remaining)
        if parsed.command == "schedule":
            return import_module(f"{__package__}.pytest_scheduling").main(remaining)
        if parsed.command == "partition":
            return import_module(f"{__package__}.ci_partitions").main(remaining)
        if parsed.command == "runner":
            return runner_main(remaining)
        return journal_main([parsed.command, *remaining])
    except (ValueError, OSError) as error:
        return utility_failure(supplied[0] if supplied else "protocol", error)


if __name__ == "__main__":
    raise SystemExit(main())
