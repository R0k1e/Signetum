"""Local authoring and journal utilities; lifecycle operations remain separate."""

import argparse
import json
import os
import sys
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
from signetum.hosts import guard_notice
from signetum.operation_cli import OperationParser, utility_failure
from signetum.serialization import contract_mapping, load_json
from signetum.source_authority import (
    authority_roots,
    committed_blob,
)
from signetum.workflow_status import workflow_status
from signetum.workspaces import current_branch, read_record, state_root

EXAMPLES = {
    "record": (
        "change record --id flaky-login --requirement REQ-001 --summary 'What was found' "
        "--reason 'Why it matters' --evidence tests/test_login.py::test_login"
    ),
    "resolve": (
        "change resolve --id fix-login --target <change>/flaky-login/observation "
        "--reason 'What resolves it' --evidence tests/test_login.py"
    ),
    "retract": (
        "change retract --id withdraw-fix --target <change>/flaky-login/observation "
        "--resolution <change>/fix-login/resolution --reason 'Why the answer was wrong'"
    ),
    "reconcile": (
        "change reconcile --id accept-decisions --reason 'Apply the approved proposals' "
        "--accept-decisions"
    ),
}


def _evidence_path(value: str) -> str:
    """A pytest node id names a test inside a file; the file is the path evidence."""
    path, separator, _ = value.partition("::")
    return path if separator and path else value


def _observation_target(sources: object, change: str, target: str) -> str:
    """Accept the observation ID or the record's --id, with or without the change prefix."""
    observed = [
        item.id
        for entry in getattr(sources, "entries", ())
        if entry.transaction.change_id == change
        for item in entry.transaction.observations
    ]
    bare = target.removeprefix(change + "/").removesuffix("/observation")
    for candidate in (target, f"{change}/{bare}/observation"):
        if candidate in observed:
            return candidate
    raise ValueError(
        f"resolve target names no observation of change {change}: {target}; expected "
        f"{change}/<id>/observation, one of: " + (", ".join(observed) or "none recorded")
    )


def _clause_history(repository: Path, sources: object, clause: str) -> dict[str, object]:
    """Every accepted revision of one clause with its reasons, approval and commits."""
    revisions: list[dict[str, object]] = []
    changes: dict[str, dict[str, object]] = {}
    authorities = getattr(sources, "authorities", {})
    root, _ = authority_roots(repository)
    for entry in getattr(sources, "entries", ()):
        for decision in entry.transaction.decisions:
            for edit in decision.clauses:
                for update in edit.updates:
                    if update.id != clause:
                        continue
                    revisions.append(
                        {
                            "version": update.version,
                            "status": update.status,
                            "action": edit.action,
                            "statement": update.statement,
                            "rationale": update.rationale,
                            "edit": edit.id,
                            "edit_reason": edit.reason,
                            "decision": decision.id,
                            "decision_reason": decision.reason,
                            "change_id": decision.change_id,
                            "applied_by": entry.transaction.id,
                        }
                    )
                    if decision.change_id in changes:
                        continue
                    record, _ = authorities.get(
                        (entry.transaction.change_id, entry.approval.commit), (None, None)
                    )
                    approval = getattr(record, "approval", None)
                    log = git_output(
                        repository,
                        "log",
                        "--format=%H%x09%ad%x09%s",
                        "--date=short",
                        "--",
                        f"{root}/{decision.change_id}",
                    )
                    changes[decision.change_id] = {
                        "change_id": decision.change_id,
                        "source": contract_mapping(record.source) if record else None,
                        "approval": contract_mapping(approval) if approval else None,
                        "commits": [
                            {"commit": commit, "date": date, "subject": subject}
                            for commit, date, subject in (
                                line.split("\t", 2) for line in log.splitlines()
                            )
                        ],
                    }
    if not revisions:
        raise ValueError(f"no accepted decision revision names clause {clause}")
    return {"clause": clause, "revisions": revisions, "changes": list(changes.values())}


def _semantic_request(
    repository: Path, options: argparse.Namespace
) -> tuple[DevelopmentTransaction, str]:
    """Bind semantic input once; the existing writer still judges every append."""
    branch = current_branch(repository)
    workspace = read_record(state_root(repository), branch)
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
        raise ValueError(
            "semantic writes require --id <stable-id> and --reason <text>, for example: "
            + EXAMPLES.get(options.operation, EXAMPLES["record"])
        )
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
                "record requires --summary <finding> and --requirement <REQ-ID> and takes no "
                "--target, --resolution, --followup or --accept-decisions; for example: "
                + EXAMPLES["record"]
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
            raise ValueError(
                "resolve requires --target <change>/<id>/observation, the observation ID that "
                "change record returned (the record's --id is accepted too), and takes no "
                "--summary, --requirement, --resolution or --accept-decisions; for example: "
                + EXAMPLES["resolve"]
            )
        if options.disposition == "resolved" and not options.evidence:
            raise ValueError(
                "resolved work requires --evidence <path-in-tree|validation-receipt-name>, a "
                "pytest node id is written as its file; or pass --disposition deferred|rejected "
                "with a --reason saying who decided and what remains owed"
            )
        body["resolutions"] = [
            {
                "id": identity + "/resolution",
                "target": _observation_target(sources, change, options.target),
                "status": options.disposition,
                "reason": options.reason,
                "evidence": [_evidence_path(item) for item in options.evidence],
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
            raise ValueError(
                "retract requires --target <observation-id> and --resolution <resolution-id> "
                "only; for example: " + EXAMPLES["retract"]
            )
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


def main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n  "
        + "\n  ".join(EXAMPLES.values())
        + "\n  change why EFFICIENCY-FAIL-001\n  status --verbose",
    )
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
            "why",
        ],
    )
    parser.add_argument("clause", nargs="?", help="why: one decision clause ID, e.g. RULE-001.")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--request", type=Path, help="Structured request JSON (atomic edits).")
    parser.add_argument("--expected-history", help="History digest of a reviewed view.")
    parser.add_argument("--change", help="Approved change ID when more than one matches.")
    parser.add_argument("--event", help="history: one event ID.")
    parser.add_argument(
        "--id", help="Stable retry identity, e.g. flaky-login; the change prefix is added."
    )
    parser.add_argument("--summary", help="record: what was found.")
    parser.add_argument("--reason", help="Why it matters, or what resolves it.")
    parser.add_argument(
        "--requirement", action="append", default=[], help="record: requirement ID, repeatable."
    )
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="A path in the current tree or a validation receipt name, repeatable; resolve "
        "writes a pytest node id path::test as its path.",
    )
    parser.add_argument(
        "--target",
        help="resolve/retract: <change>/<id>/observation as change record returned it, or "
        "that record's --id.",
    )
    parser.add_argument(
        "--disposition", choices=["resolved", "rejected", "deferred"], default="resolved"
    )
    parser.add_argument("--followup", help="deferred: change-id[#REQ-ID] of an approved change.")
    parser.add_argument("--resolution", help="retract: the exact prior resolution ID.")
    parser.add_argument("--accept-decisions", action="store_true")
    parser.add_argument(
        "--verbose", action="store_true", help="status: include resolved observations."
    )
    sources = None
    try:
        options = parser.parse_args(arguments)
        if (options.clause is not None) != (options.operation == "why"):
            raise ValueError(
                "why requires exactly one clause ID, e.g. change why RULE-001; "
                "other operations take no positional argument"
            )
        if options.verbose and options.operation != "status":
            raise ValueError("only status accepts --verbose")
        if options.operation == "why":
            sources = read_sources(options.repository)
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "passed",
                        "history_digest": sources.history_digest,
                        **_clause_history(options.repository, sources, options.clause),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
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
                    verbose=options.verbose,
                )
            )
            installed = os.environ.get("SIGNETUM_SKILL")
            if installed:
                root = Path(git_output(options.repository, "rev-parse", "--show-toplevel"))
                notice = guard_notice(Path(installed), root)
            else:
                notice = None
            if notice is not None:
                payload["guard"] = notice
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
