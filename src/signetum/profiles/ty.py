"""Translate ty GitLab output into the generic diagnostic multiset protocol."""

import json
from pathlib import Path

from signetum.validation.diagnostic_protocol import diagnostic_multiset
from signetum.validation.execution import ValidationInfrastructureError
from signetum.validation.process import run_command


def ty_document(repository: Path) -> str:
    result = run_command(
        repository, ("ty", "check", "--output-format", "gitlab"), timeout_seconds=1800
    )
    if result.returncode not in (0, 1):
        raise ValidationInfrastructureError(f"ty did not execute: {result.stdout}{result.stderr}")
    try:
        report = json.loads(result.stdout)
        if not isinstance(report, list):
            raise ValueError("expected GitLab diagnostic array")
        diagnostics = []
        for issue in report:
            location = issue["location"]
            path = Path(location["path"])
            relative = (
                path.resolve().relative_to(repository.resolve()) if path.is_absolute() else path
            )
            begin = location["positions"]["begin"]
            diagnostics.append(
                {
                    "file": relative.as_posix(),
                    "rule": issue["check_name"],
                    "message": issue["description"],
                    "line": begin["line"],
                    "column": begin["column"],
                }
            )
        document = json.dumps({"schema_version": 1, "diagnostics": diagnostics})
        diagnostic_multiset(document)
        return document
    except (ValueError, KeyError, TypeError) as error:
        raise ValidationInfrastructureError(f"invalid ty diagnostic report: {error}") from error


if __name__ == "__main__":
    print(ty_document(Path.cwd()))
