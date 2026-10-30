"""Pure relation checks for the consolidated change authority."""

from signetum.change_record import ChangeRecord, validate_change_record
from signetum.traceability.validator import TraceabilityIssue


def record_issues(records: tuple[tuple[str, ChangeRecord], ...]) -> tuple[TraceabilityIssue, ...]:
    by_id = {record.id: record for _, record in records}
    issues: list[TraceabilityIssue] = []
    for path, record in records:
        validate_change_record(record)
        for transfer in record.contract.transferred:
            change, separator, requirement = transfer.target.partition("/")
            target = by_id.get(change)
            if (
                not separator
                or change == record.id
                or target is None
                or target.status != "active"
                or requirement not in {item.id for item in target.contract.requirements}
            ):
                issues.append(
                    TraceabilityIssue(
                        code="invalid-transfer",
                        file=path,
                        field="change.contract.transferred",
                        reason=f"transfer {transfer.id} requires an active follow-up requirement",
                    )
                )
    return tuple(issues)
