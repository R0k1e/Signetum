"""Current committed source must qualify before any lifecycle gate runs."""

import subprocess  # nosec B404 -- resolved Git with explicit arguments, never a shell
from pathlib import Path
from shutil import which

from signetum.change.scope import (
    ChangeError,
    changed_commitments,
    delivery_scope,
    read_package,
    require_member_changes,
)
from signetum.development_store import DevelopmentReviewError, reconciliation_summary
from signetum.manifest import RepositoryManifest
from signetum.operations import AdmissionError


def stable_patch_id(repository: Path, base: str, source: str) -> str:
    """The stable patch identity of ``base..source``. Admission and import share it."""

    git = which("git")
    if git is None:
        raise AdmissionError("git diff failed", expected="restore the Git executable and retry")
    # run_git captures text. A binary patch has to stay bytes, so this call uses
    # the same resolved Git executable and explicit argv without that boundary.
    diff = subprocess.run(  # noqa: S603  # nosec B603 -- resolved Git, explicit argv, no shell
        (git, "-C", str(repository), "diff", "--binary", f"{base}..{source}"),
        check=False,
        capture_output=True,
    )
    if diff.returncode != 0:
        raise AdmissionError(diff.stderr.decode(errors="replace").strip() or "git diff failed")
    identified = subprocess.run(  # noqa: S603  # nosec B603 -- resolved Git, explicit argv, no shell
        (git, "patch-id", "--stable"),
        input=diff.stdout,
        check=False,
        capture_output=True,
    )
    if identified.returncode != 0:
        raise AdmissionError(
            identified.stderr.decode(errors="replace").strip() or "stable patch-id failed"
        )
    output = identified.stdout.decode().split()
    if not output:
        raise AdmissionError("member has no stable patch identity")
    return output[0]


def require_source_admission(
    repository: Path, manifest: RepositoryManifest, base: str, tip: str, *, member: bool = False
) -> tuple[str, ...]:
    """Use the same package, ancestry and standing-observation verdict everywhere."""
    try:
        if member:
            changes = require_member_changes(repository, manifest, base, tip)
        else:
            scope = delivery_scope(repository, manifest, base, tip)
            rewritten = changed_commitments(repository, manifest, base, tip, scope)
            if rewritten:
                raise ChangeError("batch rewrites delivered commitments: " + ", ".join(rewritten))
            changes = tuple(
                sorted(
                    {
                        *scope.first_delivered,
                        *(item.change_id for item in scope.previously_delivered),
                    }
                )
            )
            for change_id in scope.first_delivered:
                read_package(repository, manifest, change_id, tip).require_approval()
        reconciliation_summary(repository, changes, commit=tip)
        return changes
    except ChangeError as error:
        raise AdmissionError(str(error), expected=error.expected) from error
    except DevelopmentReviewError as error:
        raise AdmissionError(str(error)) from error
