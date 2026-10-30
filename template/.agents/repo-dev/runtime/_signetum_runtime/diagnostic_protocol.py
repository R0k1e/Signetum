# Generated from signetum.validation.diagnostic_protocol; edit the engine source and regenerate.
"""Tool-neutral, position-independent diagnostic multisets."""

import json
from collections import Counter
from pathlib import PurePosixPath

from .execution import ValidationInfrastructureError


def diagnostic_multiset(document: str) -> Counter[tuple[str, str, str]]:
    try:
        raw = json.loads(document)
        if (
            not isinstance(raw, dict)
            or set(raw) != {"schema_version", "diagnostics"}
            or raw["schema_version"] != 1
            or type(raw["schema_version"]) is not int
            or not isinstance(raw["diagnostics"], list)
        ):
            raise ValueError("expected diagnostic document version 1")
        result: Counter[tuple[str, str, str]] = Counter()
        for item in raw["diagnostics"]:
            if (
                not isinstance(item, dict)
                or set(item) - {"file", "rule", "message", "line", "column"}
                or any(
                    not isinstance(item.get(key), str) or not item[key]
                    for key in ("file", "rule", "message")
                )
            ):
                raise ValueError("invalid diagnostic fields")
            path = PurePosixPath(item["file"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("diagnostic file must be repository relative")
            for position in ("line", "column"):
                if position in item and (type(item[position]) is not int or item[position] < 1):
                    raise ValueError("invalid diagnostic position")
            result[(item["file"], item["rule"], item["message"])] += 1
        return result
    except (ValueError, KeyError, TypeError) as error:
        raise ValidationInfrastructureError(f"invalid diagnostic document: {error}") from error
