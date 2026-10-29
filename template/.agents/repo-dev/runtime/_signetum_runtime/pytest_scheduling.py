# Generated from signetum.pytest_scheduling; edit the engine source and regenerate.
"""Pytest-specific static shared groups, separate from language-neutral partitioning."""

import ast
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from .operation_cli import OperationParser, utility_failure


def shared_file_groups(files: dict[str, bytes]) -> tuple[tuple[str, ...], ...]:
    groups: dict[str, set[str]] = defaultdict(set)
    for path, source in sorted(files.items()):
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as error:
            raise ValueError("unparseable pytest partition source: " + path) from error
        constants = {
            target.id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
                or node.func.attr != "xdist_group"
            ):
                continue
            value = (
                node.args[0]
                if node.args
                else next(
                    (kw.value for kw in node.keywords if kw.arg == "name"),
                    ast.Constant(value="default"),
                )
            )
            name = (
                value.value
                if isinstance(value, ast.Constant)
                else constants.get(value.id)
                if isinstance(value, ast.Name)
                else None
            )
            if not isinstance(name, str) or not name:
                raise ValueError(f"unresolved pytest shared group: {path}:{node.lineno}")
            groups[name].add(path)
    return tuple(tuple(sorted(paths)) for _, paths in sorted(groups.items()))


def derive_weights(
    log: str, *, by_file: bool = False, minimum_seconds: float = 0
) -> dict[str, float]:
    """Reuse pytest duration output, rather than maintain another timing inventory."""
    if not math.isfinite(minimum_seconds) or minimum_seconds < 0:
        raise ValueError("minimum duration must be nonnegative and finite")
    weights: dict[str, float] = {}
    for line in log.splitlines():
        matched = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s+(?:setup|call|teardown)\s+(\S+)\s*", line)
        if matched is None:
            continue
        duration = float(matched[1])
        node = matched[2]
        marker = node.rfind("@")
        unit = (
            node.split("::", 1)[0]
            if by_file
            else node[marker + 1 :]
            if marker > max(node.rfind("]"), node.rfind("::"))
            else node
        )
        weights[unit] = weights.get(unit, 0) + duration
    return {
        unit: seconds
        for unit, seconds in sorted(weights.items())
        if seconds > 0 and seconds >= minimum_seconds
    }


def main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(
        description="Derive optional cost hints from existing pytest duration output."
    )
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--by-file", action="store_true")
    parser.add_argument("--minimum-seconds", type=float, default=0)
    try:
        options = parser.parse_args(arguments)
        weights = derive_weights(
            options.log.read_text(),
            by_file=options.by_file,
            minimum_seconds=options.minimum_seconds,
        )
        if not weights:
            raise ValueError(
                "log contains no qualifying duration observations; use existing --durations output"
            )
        with options.output.open("x", encoding="utf-8") as output:
            json.dump(weights, output, sort_keys=True)
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "derived",
                    "units": len(weights),
                    "output": str(options.output),
                }
            )
        )
        return 0
    except (ValueError, OSError) as error:
        return utility_failure("schedule", error)
