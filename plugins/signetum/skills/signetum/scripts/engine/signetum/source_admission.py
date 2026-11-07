"""Current committed source must qualify before any lifecycle gate runs."""

from pathlib import Path

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
        raise AdmissionError(str(error), expected=error.expected, fields=error.fields) from error
    except DevelopmentReviewError as error:
        raise AdmissionError(str(error)) from error
