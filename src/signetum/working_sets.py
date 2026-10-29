"""Read explicit historical constraint tables without manufacturing decisions."""

import re
from dataclasses import dataclass

from signetum.contract_values import FrozenContract
from signetum.decision_clauses import Text


@dataclass(frozen=True, kw_only=True)
class ConstraintRow(FrozenContract):
    topic: Text
    start_line: int
    end_line: int
    do_not: Text
    because: Text


@dataclass(frozen=True, kw_only=True)
class WorkingSetIssue(FrozenContract):
    line: int
    code: Text
    reason: Text


@dataclass(frozen=True, kw_only=True)
class WorkingSetSource(FrozenContract):
    id: Text
    path: Text
    blob: Text
    format: Text
    status: Text = "declared_working_set"
    context: str
    rows: tuple[ConstraintRow, ...]
    issues: tuple[WorkingSetIssue, ...]


def _indented_code(line: str) -> bool:
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip(" ")) >= 4


def _separator(cells: tuple[str, ...] | None) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells or ())


def _cells(line: str) -> tuple[str, ...] | None:
    if _indented_code(line):
        return None
    value = line.strip()
    if not value.startswith("|") or not value.endswith("|"):
        return None
    cells, current, escapes = [], [], 0
    for char in value[1:-1]:
        if char == "|" and escapes % 2 == 0:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        escapes = escapes + 1 if char == "\\" else 0
    return (*cells, "".join(current).strip())


def parse_working_set(*, identity: str, path: str, blob: str, text: str) -> WorkingSetSource:
    """Retain exact cell text and source lines; incomplete rows stay unresolved."""
    lines = text.splitlines()
    rows, issues = [], []
    topic = "Unclassified"
    table = False
    fence: tuple[str, int] | None = None
    first_table = len(lines)
    skip_separator = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if _indented_code(line):
            table = False
            continue
        if fence is not None:
            marker, length = fence
            if re.fullmatch(re.escape(marker) + "{" + str(length) + r",}\s*", stripped):
                fence = None
            continue
        opening = re.fullmatch(r"(`{3,}|~{3,})(.*)", stripped)
        if opening is not None and (opening.group(1)[0] != "`" or "`" not in opening.group(2)):
            fence = (opening.group(1)[0], len(opening.group(1)))
            table = False
            continue
        if stripped.startswith("#"):
            topic = stripped.lstrip("#").strip() or "Unclassified"
            table = False
        cells = _cells(line)
        if cells == ("do_not", "because"):
            first_table = min(first_table, index)
            separator = _cells(lines[index + 1]) if index + 1 < len(lines) else None
            table = separator is not None and len(separator) == 2 and _separator(separator)
            skip_separator = table
            if not table:
                issues.append(
                    WorkingSetIssue(
                        line=index + 1,
                        code="ambiguous_working_set_table",
                        reason="The declared constraint header has no valid two-column separator.",
                    )
                )
            continue
        if cells is not None and ("do_not" in cells or "because" in cells):
            separator = _cells(lines[index + 1]) if index + 1 < len(lines) else None
            if _separator(separator):
                table = False
                issues.append(
                    WorkingSetIssue(
                        line=index + 1,
                        code="ambiguous_working_set_table",
                        reason="Unsupported constraint columns require explicit review; "
                        "do not discard their meaning.",
                    )
                )
                continue
        if skip_separator:
            skip_separator = False
            continue
        if not table:
            continue
        if cells is None:
            table = False
            continue
        if len(cells) != 2 or not all(cells):
            issues.append(
                WorkingSetIssue(
                    line=index + 1,
                    code="ambiguous_working_set_row",
                    reason="Preserve the source row for review; "
                    "its prohibition and basis are not both explicit.",
                )
            )
            continue
        rows.append(
            ConstraintRow(
                topic=topic,
                start_line=index + 1,
                end_line=index + 1,
                do_not=cells[0],
                because=cells[1],
            )
        )
    if not rows:
        issues.append(
            WorkingSetIssue(
                line=1,
                code="unmapped_working_set",
                reason="No complete declared do_not/because row could be mapped; "
                "do not infer its rules.",
            )
        )
    return WorkingSetSource(
        id=identity,
        path=path,
        blob=blob,
        format="markdown-constraints@1",
        context="\n".join(lines[:first_table]),
        rows=tuple(rows),
        issues=tuple(issues),
    )
