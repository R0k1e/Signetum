"""Project authorized decision transactions into one current working set.

Approval verification and journal persistence belong to the repository boundary.
Input order is not authority: declared predecessors determine replay order and
concurrent writes are refused instead of picking a winner by filename or time.
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Annotated, Literal

from signetum.change.models import Identifier
from signetum.contract_values import FrozenContract
from signetum.decision_clauses import (
    DecisionEdit,
    DecisionEditError,
    EffectiveClause,
    Text,
    Version,
    apply_decision_edits,
)
from signetum.serialization import Constraints, contract_mapping, dataclass_from_mapping, load_json


@dataclass(frozen=True, kw_only=True)
class TopicRevision(FrozenContract):
    id: Identifier
    version: Version
    summary: Text
    boundaries: tuple[Text, ...] = ()
    requires: tuple[Identifier, ...] = ()


@dataclass(frozen=True, kw_only=True)
class TopicEdit(FrozenContract):
    expected_version: Annotated[int, Constraints(minimum=0)]
    revision: TopicRevision


@dataclass(frozen=True, kw_only=True)
class EffectiveTopic(FrozenContract):
    revision: TopicRevision
    source_event: Identifier


@dataclass(frozen=True, kw_only=True)
class DecisionTransaction(FrozenContract):
    id: Identifier
    change_id: Identifier
    authority: Text
    reason: Text
    parents: tuple[Identifier, ...] = ()
    clauses: tuple[DecisionEdit, ...] = ()
    topics: tuple[TopicEdit, ...] = ()


@dataclass(frozen=True, kw_only=True)
class DecisionWorkingSet(FrozenContract):
    schema_version: Literal[1] = 1
    history_digest: Text
    topics: tuple[EffectiveTopic, ...]
    clauses: tuple[EffectiveClause, ...]


@dataclass(frozen=True, kw_only=True)
class TransactionProposal(FrozenContract):
    schema_version: Literal[1]
    transaction: DecisionTransaction


def _writes(event: DecisionTransaction) -> frozenset[tuple[str, str]]:
    keys = [("topic", item.revision.id) for item in event.topics]
    keys.extend(("clause", clause.id) for edit in event.clauses for clause in edit.updates)
    if not keys or len(keys) != len(set(keys)):
        raise DecisionEditError("a transaction must name nonempty unique writes")
    if any(
        edit.change_id != event.change_id or edit.authority != event.authority
        for edit in event.clauses
    ):
        raise DecisionEditError("a transaction cannot change the owning change or authority")
    return frozenset(keys)


def _topic_relations(
    topics: dict[str, EffectiveTopic], clauses: tuple[EffectiveClause, ...]
) -> None:
    for item in clauses:
        if item.revision.status == "active" and item.revision.topic not in topics:
            raise DecisionEditError(f"active clause has no topic context: {item.revision.id}")
    graph = {key: item.revision.requires for key, item in topics.items()}
    if any(dependency not in graph for values in graph.values() for dependency in values):
        raise DecisionEditError("topic relationship names absent context")
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise DecisionEditError("cyclic topic relationship") from error


def project_decision_history(events: tuple[DecisionTransaction, ...]) -> DecisionWorkingSet:
    """Build a deterministic current set, without trusting a separately edited summary."""
    by_id = {event.id: event for event in events}
    edit_ids = [edit.id for event in events for edit in event.clauses]
    if (
        len(by_id) != len(events)
        or len(edit_ids) != len(set(edit_ids))
        or set(edit_ids) & set(by_id)
    ):
        raise DecisionEditError("duplicate decision transaction or edit identity")
    writes = {event.id: _writes(event) for event in events}
    for event in events:
        if len(set(event.parents)) != len(event.parents) or any(
            parent not in by_id for parent in event.parents
        ):
            raise DecisionEditError("transaction predecessors must be present and unique")
    graph = TopologicalSorter({event.id: event.parents for event in events})
    try:
        graph.prepare()
    except CycleError as error:
        raise DecisionEditError("cyclic decision transaction history") from error
    current: tuple[EffectiveClause, ...] = ()
    topics: dict[str, EffectiveTopic] = {}
    while graph.is_active():
        ready = sorted(graph.get_ready())
        claimed: set[tuple[str, str]] = set()
        for identity in ready:
            if claimed & writes[identity]:
                raise DecisionEditError(
                    "concurrent decision writes require explicit reconciliation"
                )
            claimed.update(writes[identity])
        for identity in ready:
            event = by_id[identity]
            for update in event.topics:
                revision = update.revision
                old = topics.get(revision.id)
                observed = old.revision.version if old else 0
                if observed != update.expected_version or revision.version != observed + 1:
                    raise DecisionEditError(f"stale topic revision: {revision.id}")
                topics[revision.id] = EffectiveTopic(revision=revision, source_event=event.id)
            current = apply_decision_edits(current, event.clauses)
            _topic_relations(topics, current)
            graph.done(identity)
    canonical = json.dumps(
        [contract_mapping(by_id[key]) for key in sorted(by_id)],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return DecisionWorkingSet(
        history_digest="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        topics=tuple(topics[key] for key in sorted(topics)),
        clauses=current,
    )


def verify_working_set(
    value: object, events: tuple[DecisionTransaction, ...]
) -> DecisionWorkingSet:
    """Refuse a stale or independently edited projection of the same history."""
    observed = dataclass_from_mapping(DecisionWorkingSet, value)
    expected = project_decision_history(events)
    if observed != expected:
        raise DecisionEditError("working set differs from its decision history")
    return expected


def main(arguments: list[str] | None = None) -> int:
    """Preview candidate history; never grant approval or update a repository."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposals", type=Path, nargs="+")
    parser.add_argument("--check-projection", type=Path)
    parsed = parser.parse_args(arguments)
    try:
        events = tuple(
            dataclass_from_mapping(TransactionProposal, load_json(line)).transaction
            for path in parsed.proposals
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        result = project_decision_history(events)
        if parsed.check_projection is not None:
            result = verify_working_set(
                load_json(parsed.check_projection.read_text(encoding="utf-8")), events
            )
    except (OSError, ValueError, TypeError) as error:
        print(
            json.dumps({"schema_version": 1, "status": "invalid", "reason": str(error)}),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": 1,
                "status": "preview",
                "working_set": contract_mapping(result),
                "projection_checked": parsed.check_projection is not None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
