"""Current committed source must qualify before any lifecycle gate runs."""

import hashlib
import json
import re
import subprocess  # nosec B404 -- resolved Git with explicit arguments, never a shell
from collections.abc import Mapping
from pathlib import Path
from shutil import which

from signetum.change.paths import changes_root
from signetum.change.scope import (
    ChangeError,
    changed_commitments,
    delivered_plans,
    delivery_scope,
    read_package,
    records_only,
    require_member_changes,
)
from signetum.development_store import DevelopmentReviewError, reconciliation_summary
from signetum.evidence.receipts import EvidenceReceipt, ReceiptError
from signetum.git import GitError, git_output
from signetum.manifest import ManifestError, RepositoryManifest, parse_manifest
from signetum.operations import AdmissionError
from signetum.serialization import ValueDecodeError, load_json
from signetum.validation.inheritance import verify_committed_inputs


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


def bind_admission_qualification(
    repository: Path, document: Mapping[str, object], content: bytes
) -> None:
    """Bind qualification bytes, plans, and patch to the declared source.

    Digest equality only proves the bytes are intact. The receipt has to name
    that source, and the operation's plans and patch have to match the approved
    source rules. Operation records call this owner for a local record and an import.
    """

    source = str(document["source"])
    base = str(document["base"])
    plans = document.get("plans")
    patch = document.get("patch_id")
    evidence = document.get("ready_evidence")
    if not isinstance(plans, list) or not isinstance(patch, str) or not isinstance(evidence, str):
        raise AdmissionError("operation qualification does not bind its source")
    try:
        payload = load_json(content.decode("utf-8"))
        if not isinstance(payload, dict) or "evidence" not in payload:
            raise ReceiptError("admitted evidence must be an object")
        receipt = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
        # Judge the source commit. The batch checkout can still hold the
        # pre-merge manifest, and live source review belongs to the member
        # checkout that already qualified this tip.
        manifest = parse_manifest(git_output(repository, "show", f"{source}:signetum.toml"))
        if receipt.identity.commit != source and not records_only(
            repository, changes_root(manifest), receipt.identity.commit, source
        ):
            raise AdmissionError("operation qualification does not bind its source")
        if receipt.execution.gates not in (("member",), ("final",)):
            raise AdmissionError("operation qualification does not bind its source")
        if evidence and Path(evidence).name == evidence:
            match = re.fullmatch(r"(?:member|final)-lifecycle-([0-9a-f]{64})\.json", evidence)
            if match and hashlib.sha256(receipt.to_json().encode()).hexdigest() != match[1]:
                raise AdmissionError("operation qualification does not bind its source")
        verify_committed_inputs(repository, receipt)
        try:
            changes = require_member_changes(
                repository, manifest, receipt.identity.base or base, source
            )
        except ChangeError as error:
            raise AdmissionError(str(error), expected=error.expected) from error
        if tuple(plans) != delivered_plans(repository, manifest, changes, source):
            raise AdmissionError("operation plans do not match the approved source")
        if patch != stable_patch_id(repository, base, source):
            raise AdmissionError("operation patch does not match the approved source")
    except AdmissionError:
        raise
    except (
        ReceiptError,
        ManifestError,
        GitError,
        OSError,
        UnicodeError,
        ValueDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ) as error:
        raise AdmissionError(
            f"operation qualification does not bind its source: {error}"
        ) from error
