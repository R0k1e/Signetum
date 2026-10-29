"""Shared readiness, exact validation and final review receipt publication."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from signetum.change.member import qualify_member
from signetum.change.paths import changes_root
from signetum.change.scope import changed_commitments, delivery_scope
from signetum.decision_identity import numbered_targets
from signetum.development_store import DevelopmentReviewError
from signetum.development_store import reconciliation_summary as source_reconciliation_summary
from signetum.deviations import DeviationError, approval_view, reconciliation_summary
from signetum.evidence.receipts import EvidenceReceipt
from signetum.execution_review import execution_review_inputs
from signetum.git import git_output
from signetum.manifest import RepositoryManifest, load_manifest
from signetum.operations import AdmissionError
from signetum.repository_selection import select_repository
from signetum.synchronization import member_contribution_paths
from signetum.validation import ValidationGraph
from signetum.validation.configuration import member_shards as select_member_shards
from signetum.validation.configuration import with_deferred_world
from signetum.validation.execution import (
    ValidationAdapter,
    ValidationExecutionError,
    ValidationInputs,
    execute_gate,
)
from signetum.validation.inheritance import find_test_inheritance
from signetum.validation.receipt_store import ReceiptStore
from signetum.validation.review import member_recovery_review, recovery_projection
from signetum.waivers import WaiverError, load_waivers
from signetum.workspaces import recorded_base, require_clean


class ValidationConfiguration(Protocol):
    def __call__(
        self, manifest: RepositoryManifest, *, member_shards: tuple[str, ...] | None = None
    ) -> tuple[ValidationGraph, ValidationInputs]:
        """Resolve the adapter's maintained profile resources into declared inputs."""


class AdapterFactory(Protocol):
    def __call__(self, repository: Path, *, member_base: str | None = None) -> ValidationAdapter:
        """Construct repository effects for the common execution owner."""


def validate_workspace(
    repository: Path,
    kind: str,
    *,
    configure: ValidationConfiguration,
    adapter_factory: AdapterFactory,
    receipt_root: Callable[[Path], Path],
    proposal_paths: Callable[[Path], tuple[str, ...]],
    check_numbering_base: Callable[[Path, str | None, str], None],
    execute: Callable[..., EvidenceReceipt] = execute_gate,
) -> dict[str, object]:
    require_clean(repository)
    source = git_output(repository, "rev-parse", "HEAD")
    manifest = load_manifest(repository / "signetum.toml")
    base = None if kind == "final" else recorded_base(repository)
    if base is not None and source == git_output(repository, "rev-parse", base):
        raise AdmissionError("source has no commits beyond the approved base")
    if base is not None:
        qualify_member(repository, manifest, base, source)
    evidence_base = recorded_base(repository) if kind == "final" else None
    scope = None
    member_recoveries = []
    if kind == "final":
        if evidence_base is None:
            raise AdmissionError("final has no recorded batch base")
        proposals = proposal_paths(repository)
        if proposals:
            raise AdmissionError(f"final refuses proposal decisions: {', '.join(proposals)}")
        check_numbering_base(repository, evidence_base, source)
        scope = delivery_scope(repository, manifest, evidence_base, source)
        rewritten = changed_commitments(repository, manifest, evidence_base, source, scope)
        if rewritten:
            raise AdmissionError(f"batch rewrites delivered commitments: {', '.join(rewritten)}")
        change_ids = scope.first_delivered
        target_moves = numbered_targets(
            repository, evidence_base, source, manifest.repository.decisions
        )

        member_recoveries = member_recovery_review(
            repository, evidence_base, source, receipt_root(repository)
        )
        try:
            review_inputs = execution_review_inputs(
                repository, manifest, evidence_base, source, receipt_root(repository)
            )
            reconciliation = reconciliation_summary(
                repository,
                tuple(review_inputs["changes"]),
                target_moves=target_moves,
                member_tips=review_inputs["member_tips"],
            )
            source_reconciliation = source_reconciliation_summary(
                repository, tuple(review_inputs["source_journals"]["changes"]), commit=source
            )
            approvals = [
                approval_view(repository, change_id, root=changes_root(manifest))
                for change_id in change_ids
            ]
        except (DeviationError, DevelopmentReviewError) as error:
            raise AdmissionError(f"execution reconciliation failed: {error}") from error
    else:
        reconciliation = None
        approvals = None
    manifest = load_manifest(repository / "signetum.toml")
    gate = "member" if kind == "member" else "final"
    declared_manifest = manifest
    selected = None
    member_shards: tuple[str, ...] | None = None
    if base is not None:
        resolved = select_repository(
            repository,
            manifest,
            member_contribution_paths(repository, base, source),
            base=base,
            source=source,
        )
        manifest, selected = resolved.manifest, resolved.selection
        member_shards, deferred = select_member_shards(manifest, selected)
        selected = with_deferred_world(selected, deferred)
    graph, initial_inputs = configure(manifest, member_shards=member_shards)
    try:
        waivers = load_waivers(repository)
    except WaiverError as error:
        raise AdmissionError(f"waiver authority is invalid: {error}") from error
    inputs = ValidationInputs(
        initial_inputs.configuration_path,
        initial_inputs.profiles,
        initial_inputs.lockfiles,
        initial_inputs.tools,
        base=git_output(repository, "rev-parse", base) if base else evidence_base,
        selection=selected,
        schema_digest=manifest.signetum.evidence_schema_digest,
        waivers=waivers,
    )
    adapter = adapter_factory(repository, member_base=base)
    inherited = (
        find_test_inheritance(
            repository,
            manifest.impact.rules,
            graph,
            inputs,
            adapter,
            receipt_root(repository),
            selector=(
                lambda paths, ancestor, tip: (
                    select_repository(
                        repository, declared_manifest, paths, base=ancestor, source=tip
                    ).selection
                )
            )
            if declared_manifest.impact.provider is not None
            else None,
        )
        if kind == "member"
        else None
    )
    receipt = execute(graph, gate, inputs, adapter, inherited=inherited)
    try:
        require_clean(repository)
    except AdmissionError as error:
        raise ValidationExecutionError(str(error)) from error
    if kind == "final":
        if evidence_base is None:
            raise AdmissionError("final has no recorded batch base")
        try:
            if (
                execution_review_inputs(
                    repository, manifest, evidence_base, source, receipt_root(repository)
                )
                != review_inputs
            ):
                raise AdmissionError(
                    "delivery review inputs changed during validation; rerun final"
                )
        except (DeviationError, DevelopmentReviewError) as error:
            raise AdmissionError(
                f"delivery review inputs changed during validation: {error}"
            ) from error
    receipt_path = ReceiptStore(receipt_root(repository)).write(gate, receipt)
    payload = {
        "schema_version": 2,
        "kind": kind,
        "source": source,
        "base": git_output(repository, "rev-parse", base) if base else evidence_base,
        "validated_at": datetime.now(UTC).isoformat(),
        "valid": True,
        "evidence": json.loads(receipt.to_json()),
    }
    if reconciliation is not None and approvals is not None and scope is not None:
        payload["delivery_review"] = {
            "inputs": review_inputs,
            "recovered_flake_defects": member_recoveries
            + recovery_projection(receipt, receipt_path, member=None),
            "approvals": approvals,
            "reconciliation": reconciliation,
            "source_reconciliation": source_reconciliation,
            "previously_delivered": [
                {"change_id": item.change_id, "paths": list(item.paths)}
                for item in scope.previously_delivered
            ],
        }
    lifecycle_receipt = receipt_path.with_name(
        receipt_path.name.replace(f"{gate}-", f"{gate}-lifecycle-")
    )
    lifecycle_receipt.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return {
        **payload,
        "status": "ready" if kind == "member" else "final",
        "receipt": str(lifecycle_receipt),
    }
