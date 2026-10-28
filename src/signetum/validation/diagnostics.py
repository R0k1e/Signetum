"""Tool-neutral corpus diagnostics and the traceability adapter."""

from __future__ import annotations

import argparse
import io
import json
from collections import Counter
from pathlib import Path, PurePosixPath

from signetum.change.scope import changes_root
from signetum.manifest import load_manifest
from signetum.status.models import EvidenceSnapshot
from signetum.traceability.boundary import TraceabilityManifest
from signetum.traceability.cli import ExitCode, query
from signetum.validation.execution import ValidationInfrastructureError


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


def traceability_document(repository: Path) -> str:
    manifest = load_manifest(repository / "signetum.toml")
    output, errors = io.StringIO(), io.StringIO()
    status = query(
        repository,
        TraceabilityManifest(
            schema_version=1,
            changes_root=changes_root(manifest),
            decision_roots=(manifest.repository.decisions,),
        ),
        EvidenceSnapshot(),
        output,
        errors,
    )
    if status not in (ExitCode.SUCCESS, ExitCode.VALIDATION_FAILURE):
        raise ValidationInfrastructureError(
            errors.getvalue() or "traceability check did not execute"
        )
    report = json.loads(output.getvalue())
    return json.dumps(
        {
            "schema_version": 1,
            "diagnostics": [
                {
                    "file": issue["file"],
                    "rule": issue["code"],
                    "message": f"{issue['field']}: {issue['reason']}",
                }
                for issue in report["issues"]
            ],
        }
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=("traceability",))
    parser.parse_args(arguments)
    print(traceability_document(Path.cwd()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
