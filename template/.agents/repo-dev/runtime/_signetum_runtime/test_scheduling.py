# Generated from signetum.test_scheduling; edit the engine source and regenerate.
"""Optional cost hints and whole-group partitioning; never verdict or membership."""

import math
from collections.abc import Mapping, Sequence


def ordered_units(
    units: Sequence[tuple[str, str]], weights: Mapping[str, float]
) -> tuple[str, ...]:
    if not isinstance(weights, Mapping) or any(
        not isinstance(name, str)
        or not name
        or type(value) not in {int, float}
        or not math.isfinite(value)
        or value <= 0
        for name, value in weights.items()
    ):
        raise ValueError("scheduling weights must be positive finite costs")
    members: dict[str, list[str]] = {}
    for unit, item in units:
        members.setdefault(unit, []).append(item)
    order = {unit: n for n, unit in enumerate(members)}
    return tuple(
        item
        for unit in sorted(members, key=lambda u: (-weights.get(u, 0), -len(members[u]), order[u]))
        for item in members[unit]
    )


def partition_units(
    files: tuple[str, ...],
    count: int,
    weights: Mapping[str, float],
    groups: tuple[tuple[str, ...], ...] = (),
) -> tuple[tuple[str, ...], ...]:
    if type(count) is not int or count < 1 or count > len(files) or len(files) != len(set(files)):
        raise ValueError(
            "partition count requires unique files and one nonempty partition per lane"
        )
    ordered_units((), weights)
    components = [{p} for p in sorted(files)]
    for group in groups:
        if not group or not set(group) <= set(files):
            raise ValueError("shared groups must name existing partition files")
        related = [c for c in components if c & set(group)]
        merged = set().union(*related)
        components = [c for c in components if not c & merged] + [merged]
    if count > len(components):
        raise ValueError("partition count exceeds independent shared groups")
    lanes: list[list[str]] = [[] for _ in range(count)]
    costs = [0.0] * count
    for component in sorted(
        components, key=lambda c: (-sum(weights.get(p, 1.0) for p in c), min(c))
    ):
        lane = min(range(count), key=lambda n: (costs[n], n))
        lanes[lane].extend(sorted(component))
        costs[lane] += sum(weights.get(p, 1.0) for p in component)
    return tuple(tuple(sorted(lane)) for lane in lanes)
