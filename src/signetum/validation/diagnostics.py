"""Tool-neutral corpus diagnostics and the traceability adapter."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from signetum.change.paths import changes_root
from signetum.manifest import load_manifest
from signetum.status.models import EvidenceSnapshot
from signetum.traceability.boundary import TraceabilityManifest
from signetum.traceability.cli import ExitCode, query
from signetum.validation.execution import ValidationInfrastructureError


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
