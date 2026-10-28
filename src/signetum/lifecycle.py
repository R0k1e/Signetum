"""Lifecycle authority for explicit Signetum batch admission."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess  # nosec B404 -- fixed tuple commands, never a shell
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Never

from signetum.change.scope import (
    ChangeError,
    changed_commitments,
    changes_root,
    delivered_plans,
    delivery_scope,
    member_contribution_paths,
    member_scope,
    require_member_changes,
)
from signetum.deviations import (
    DeviationError,
    approval_view,
    changes_naming_member,
    reconciliation_summary,
)
from signetum.evidence.receipts import EvidenceReceipt, ReceiptError, ValidationSelection
from signetum.git import GitError, git_output, run_git
from signetum.impact import select_paths
from signetum.manifest import ManifestError, RepositoryManifest, load_manifest
from signetum.operations import (
    EXIT_CODES,
    AdmissionError,
    InfrastructureError,
    MergeConflict,
    OperationError,
    OperationFailed,
    OperationResult,
    OperationStatus,
)
from signetum.policy import delivery_policy
from signetum.provenance import attested_base as _attested_base
from signetum.provenance import members_and_plans as _delivery_provenance
from signetum.validation import (
    ValidationGraphError,
)
from signetum.validation.execution import (
    ValidationExecutionError,
    ValidationInfrastructureError,
    ValidationInputs,
    build_evidence_identity,
    execute_gate,
    require_recovery_limit,
)
from signetum.validation.inheritance import find_test_inheritance
from signetum.validation.ratchet import ratchet_baseline
from signetum.validation.repository import (
    ReceiptStore,
    RepositoryValidationAdapter,
    run_diagnostic_gate,
    with_recovery_history,
)
from signetum.validation.repository import configured_validation as _runtime_validation
from signetum.validation.review import member_recovery_review, recovery_projection
from signetum.waivers import WaiverError, load_waivers
from signetum.workspace_operations import (
    batch_discard,
    cleanup,
    fresh_delivery,
    open_workspace,
    workspace_open,
    workspace_sync,
    worktree_prepare,
)
from signetum.workspace_operations import cleanup_delivered as _cleanup_delivered_worktrees
from signetum.workspaces import (
    WorkspaceError,
    claim_change,
    read_record,
)
from signetum.workspaces import (
    branch_name as _branch,
)
from signetum.workspaces import (
    exclusive_batch as _exclusive_batch,
)
from signetum.workspaces import (
    recorded_base as _recorded_base,
)
from signetum.workspaces import (
    require_clean as _require_clean,
)
from signetum.workspaces import (
    require_no_merge as _require_no_merge,
)
from signetum.workspaces import (
    state_root as _state_root,
)


def _receipt_root(repository: Path) -> Path:
    root = _state_root(repository) / "validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _selection(repository: Path, base: str, manifest: RepositoryManifest) -> ValidationSelection:
    files = member_contribution_paths(repository, base, _git(repository, "rev-parse", "HEAD"))
    return select_paths(files, manifest)


def _member_shards(
    manifest: RepositoryManifest, selection: ValidationSelection, *, member_closure: bool = True
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the member shards to execute and the world shards left to final.

    Member closure stays a function of the observed tree, so a world shard
    reached through an impact rule or a composed gate is deferred rather than
    allowed to make an unrelated member unclosable.
    """

    gate_shards = {gate.name: gate.shards for gate in manifest.validation.gates}
    world = {item.name for item in manifest.validation.shards if item.evidence == "world"}
    selected: list[str] = list(manifest.validation.member_required) if member_closure else []
    deferred: list[str] = []

    def admit(name: str) -> None:
        if name in world:
            if name not in deferred:
                deferred.append(name)
            return
        if name not in selected:
            selected.append(name)

    for shard in selection.shards:
        admit(shard)
    for gate in selection.gates:
        for shard in gate_shards.get(gate, ()):
            admit(shard)
    if selection.unexplained and member_closure:
        for shard in gate_shards["member"]:
            admit(shard)
    return tuple(selected), tuple(sorted(deferred))


def changed(repository: Path, explain: bool, *, validate_only: bool = False) -> dict[str, object]:
    _require_clean(repository)
    base = _recorded_base(repository)
    source = _git(repository, "rev-parse", "HEAD")
    manifest = load_manifest(repository / "signetum.toml")
    files = member_contribution_paths(repository, base, source)
    selected = select_paths(files, manifest)
    if not files:
        raise AdmissionError("workspace has no committed contribution to validate")
    member_shards, deferred = _member_shards(manifest, selected, member_closure=False)
    graph, inputs = _runtime_validation(manifest, member_shards=member_shards)
    checks = (
        {"executed": []}
        if validate_only
        else run_diagnostic_gate(repository, graph, "member", member_base=base, tools=inputs.tools)
    )
    if _git(repository, "rev-parse", "HEAD") != source:
        raise ValidationExecutionError("diagnostic changed the committed source")
    try:
        _require_clean(repository)
    except AdmissionError as error:
        raise ValidationExecutionError("diagnostic changed working files") from error
    return {
        "schema_version": 1,
        "status": "selection-only"
        if validate_only
        else ("changed" if checks["executed"] else "nothing-selected"),
        "base": base,
        "source": source,
        "files": files,
        "selection": json.loads(json.dumps(selected.__dict__)),
        "rules": selected.rules,
        "profiles": selected.profiles,
        "gates": selected.gates,
        "shards": selected.shards,
        "unexplained": selected.unexplained,
        "requires_final": selected.requires_final,
        "explain": explain,
        "executed": checks["executed"],
        "checks_started": bool(checks["executed"]),
        "shard_details": checks.get("shard_details", {}),
        "recovered_flake_defects": checks.get("recovered_flake_defects", []),
        "deferred_world_shards": deferred,
    }


def validate(repository: Path, kind: str) -> dict[str, object]:
    if kind != "final":
        return _validate_held(repository, kind)
    with _exclusive_batch(repository):
        record = read_record(_state_root(repository), _branch(repository))
        if record.kind != "batch":
            raise AdmissionError("final requires a registered batch workspace")
        _require_no_merge(repository)
        _require_clean(repository)
        proposals = _proposal_paths(repository)
        if proposals:
            raise AdmissionError(f"final refuses proposal decisions: {', '.join(proposals)}")
        base = _recorded_base(repository)
        numbered = _number_proposals(repository, base)
        result = _validate_held(repository, kind)
        return {**result, "numbered": numbered}


def _validate_held(repository: Path, kind: str) -> dict[str, object]:
    _require_clean(repository)
    source = _git(repository, "rev-parse", "HEAD")
    manifest = load_manifest(repository / "signetum.toml")
    base = None if kind == "final" else _recorded_base(repository)
    if base is not None and source == _git(repository, "rev-parse", base):
        raise AdmissionError("source has no commits beyond the approved base")
    if base is not None:
        if read_record(_state_root(repository), _branch(repository)).kind != "member":
            raise AdmissionError("ready requires a registered member workspace")
        try:
            require_member_changes(
                repository,
                manifest,
                base,
                source,
                changes_naming_member(repository, _branch(repository)),
            )
            for change_id in member_scope(repository, manifest, base, source).first_delivered:
                claim_change(_state_root(repository), change_id, _branch(repository))
        except (ChangeError, DeviationError, WorkspaceError) as error:
            raise AdmissionError(str(error)) from error
    evidence_base = _recorded_base(repository) if kind == "final" else None
    scope = None
    member_recoveries = []
    if kind == "final":
        if evidence_base is None:
            raise AdmissionError("final has no recorded batch base")
        proposals = _proposal_paths(repository)
        if proposals:
            raise AdmissionError(f"final refuses proposal decisions: {', '.join(proposals)}")
        _require_numbering_base(repository, evidence_base, source)
        scope = delivery_scope(repository, manifest, evidence_base, source)
        rewritten = changed_commitments(repository, manifest, evidence_base, source, scope)
        if rewritten:
            raise AdmissionError(f"batch rewrites delivered commitments: {', '.join(rewritten)}")
        change_ids = scope.first_delivered
        member_recoveries = member_recovery_review(
            repository, evidence_base, source, _receipt_root(repository)
        )
        try:
            reconciliation = reconciliation_summary(repository, change_ids)
            approvals = [
                approval_view(repository, change_id, root=changes_root(manifest))
                for change_id in change_ids
            ]
        except DeviationError as error:
            raise AdmissionError(f"deviation reconciliation failed: {error}") from error
    else:
        reconciliation = None
        approvals = None
    manifest = load_manifest(repository / "signetum.toml")
    gate = "member" if kind == "member" else "final"
    selected = _selection(repository, base, manifest) if base is not None else None
    member_shards: tuple[str, ...] | None = None
    if selected is not None:
        member_shards, deferred = _member_shards(manifest, selected)
        if deferred:
            selected = replace(
                selected,
                reasons=selected.reasons
                + tuple(f"world shard {name} deferred to final" for name in deferred),
            )
    graph, initial_inputs = _runtime_validation(manifest, member_shards=member_shards)
    try:
        waivers = load_waivers(repository)
    except WaiverError as error:
        raise AdmissionError(f"waiver authority is invalid: {error}") from error
    inputs = ValidationInputs(
        initial_inputs.configuration_path,
        initial_inputs.profiles,
        initial_inputs.lockfiles,
        initial_inputs.tools,
        base=_git(repository, "rev-parse", base) if base else evidence_base,
        selection=selected,
        schema_digest=manifest.signetum.evidence_schema_digest,
        waivers=waivers,
    )
    inputs = with_recovery_history(
        replace(
            inputs,
            recovery_threshold=initial_inputs.recovery_threshold,
            recovery_window=initial_inputs.recovery_window,
        ),
        _receipt_root(repository),
    )
    adapter = RepositoryValidationAdapter(repository, member_base=base)
    inherited = (
        find_test_inheritance(
            repository, manifest, graph, inputs, adapter, _receipt_root(repository)
        )
        if kind == "member"
        else None
    )
    receipt = execute_gate(graph, gate, inputs, adapter, inherited=inherited)
    adapter.require_clean()
    receipt_path = ReceiptStore(_receipt_root(repository)).write(gate, receipt)
    payload = {
        "schema_version": 2,
        "kind": kind,
        "source": source,
        "base": _git(repository, "rev-parse", base) if base else evidence_base,
        "validated_at": datetime.now(UTC).isoformat(),
        "valid": True,
        "evidence": json.loads(receipt.to_json()),
    }
    if reconciliation is not None and approvals is not None and scope is not None:
        payload["delivery_review"] = {
            "recovered_flake_defects": member_recoveries
            + recovery_projection(receipt, receipt_path, member=None),
            "approvals": approvals,
            "reconciliation": reconciliation,
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


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    try:
        return git_output(repository, *arguments, check=check)
    except GitError as error:
        raise AdmissionError(str(error)) from error


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    git = _git_executable()
    completed = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "merge-base", "--is-ancestor", ancestor, descendant),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in (0, 1):
        raise AdmissionError(completed.stderr.strip() or "merge-base failed")
    return completed.returncode == 0


def _admission_evidence(member: Path, tip: str, manifest: RepositoryManifest) -> str:
    """Require successful tree evidence for this exact member and its inputs."""

    base = _recorded_base(member)
    if not _is_ancestor(member, base, tip):
        raise AdmissionError("member does not descend from its recorded base")
    selection = _selection(member, base, manifest)
    required_names, _ = _member_shards(manifest, selection)
    graph, inputs = _runtime_validation(manifest, member_shards=required_names)
    closure = set(graph.execution_order("member"))
    required = frozenset(shard.digest for shard in graph.shards if shard.name in closure)
    ratchets = tuple(
        shard.name for shard in graph.shards if shard.name in closure and shard.ratchet_command
    )
    qualified_base = ratchet_baseline(member, base, tip) if ratchets else None
    adapter = RepositoryValidationAdapter(member)
    member_identity = build_evidence_identity(graph, replace(inputs, base=base), adapter)
    final_graph, _ = _runtime_validation(manifest)
    expected = {
        "member": member_identity,
        "final": replace(member_identity, graph=final_graph.digest),
    }
    for path in sorted(_receipt_root(member).glob("*-lifecycle-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            receipt = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ReceiptError):
            continue
        if not receipt.valid or receipt.schema_digest != manifest.signetum.evidence_schema_digest:
            continue
        if len(receipt.execution.gates) != 1:
            continue
        identity = expected.get(receipt.execution.gates[0])
        if identity is None or identity.commit != tip or receipt.identity != identity:
            continue
        if receipt.execution.gates == ("member",) and ratchets:
            details = receipt.extensions.get("shard_details", {})
            if not isinstance(details, dict):
                continue
            qualified = True
            for name in ratchets:
                detail = details.get(name)
                report = detail.get("ratchet") if isinstance(detail, dict) else None
                if not isinstance(report, dict) or report.get("baseline") != qualified_base:
                    qualified = False
                    break
            if not qualified:
                continue
        proven = frozenset(
            outcome.command_digest
            for outcome in receipt.execution.shards
            if outcome.evidence == "tree" and outcome.status == "passed"
        )
        if required <= proven:
            if receipt.execution.gates == ("final",):
                policy_inputs = with_recovery_history(
                    inputs,
                    _receipt_root(member),
                    exclude=path.with_name(path.name.replace("-lifecycle-", "-")),
                )
                require_recovery_limit(
                    receipt.extensions.get("recovered_flake_defects", []), policy_inputs
                )
            return path.name
    raise AdmissionError(
        "member has no evidence proving its selected validation for the exact tip and inputs"
    )


def _stable_patch_id(repository: Path, base: str, source: str) -> str:
    git = _git_executable()
    diff = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "diff", "--binary", f"{base}..{source}"),
        check=False,
        capture_output=True,
    )
    if diff.returncode != 0:
        raise AdmissionError(diff.stderr.decode(errors="replace").strip() or "git diff failed")
    identified = subprocess.run(  # nosec B603
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


def _proposal_paths(repository: Path) -> tuple[str, ...]:
    """Return every decision still declaring itself a proposal.

    A proposal is identified by its declared status, not by its file name: an
    accepted decision may stay unnumbered, so a name alone cannot say whether
    one is still awaiting acceptance.
    """

    paths: list[str] = []
    for line in _git(repository, "ls-files", "*ADP-*.md").splitlines():
        if not line:
            continue
        candidate = repository / line
        try:
            head = candidate.read_text(encoding="utf-8")[:512]
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"^Status:\s*Proposed\s*$", head, re.MULTILINE):
            paths.append(line)
    return tuple(paths)


def _require_numbering_base(repository: Path, base: str | None, tip: str) -> None:
    if base is None:
        return
    messages = _git(repository, "log", "--first-parent", "--format=%B%x00", f"{base}..{tip}")
    numbering_bases = re.findall(r"^Signetum-Decision-Base:\s*(\S+)$", messages, re.MULTILINE)
    if numbering_bases and set(numbering_bases) != {base}:
        raise AdmissionError("decision numbering is bound to a different delivery base")


def _record_supersession(batch: Path, formal_path: Path) -> None:
    """Write the reciprocal entry into every decision this one replaces.

    A supersession only the successor records leaves every reader of the
    replaced decision believing it still stands.
    """

    decision = batch / formal_path
    declared = re.search(
        r"^Supersedes:\s*(.+)$", decision.read_text(encoding="utf-8"), re.MULTILINE
    )
    if declared is None:
        return
    for reference in (item.strip() for item in declared.group(1).split(",")):
        if not reference or reference.lower() == "none":
            continue
        target = decision.parent / Path(reference).name
        if not target.is_file():
            raise AdmissionError(f"decision supersedes an absent decision: {reference}")
        content = target.read_text(encoding="utf-8")
        edge = re.search(r"^Superseded by:(.*)$", content, re.MULTILINE)
        if edge is None:
            raise AdmissionError(f"decision declares no supersession field: {reference}")
        successors = tuple(
            value.strip()
            for value in edge.group(1).split(",")
            if value.strip() and value.strip().lower() != "none"
        )
        successors = tuple(dict.fromkeys((*successors, formal_path.name)))
        updated = (
            content[: edge.start()]
            + "Superseded by: "
            + ", ".join(successors)
            + content[edge.end() :]
        )
        target.write_text(updated, encoding="utf-8")


def _number_proposals(batch: Path, base: str) -> list[dict[str, str]]:
    manifest = load_manifest(batch / "signetum.toml")
    directory = manifest.repository.decisions.rstrip("/")
    base_names = _git(batch, "ls-tree", "-r", "--name-only", base).splitlines()
    proposals = tuple(
        path
        for path in _git(batch, "ls-files", f"{directory}/ADP-*.md").splitlines()
        if not re.fullmatch(r"ADP-\d{4}-.+\.md", Path(path).name)
        and re.search(
            r"^Status:\s*Accepted\s*$",
            (batch / path).read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        and not (
            path in base_names
            and re.search(
                r"^Status:\s*Accepted\s*$",
                _git(batch, "show", f"{base}:{path}"),
                re.MULTILINE,
            )
        )
    )
    if not proposals:
        return []
    _, remote_tip = fresh_delivery(batch)
    remote_names = _git(batch, "ls-tree", "-r", "--name-only", remote_tip).splitlines()
    used = [
        int(match.group(1))
        for path in (*base_names, *remote_names, *_git(batch, "ls-files").splitlines())
        if path.startswith(directory + "/")
        if (match := re.search(r"(?:^|/)ADP-(\d{4})-[^/]+\.md$", path))
    ]
    next_number = max(used, default=0) + 1
    rewrites: list[dict[str, str]] = []
    for proposal in sorted(proposals):
        proposal_path = Path(proposal)
        slug = proposal_path.name.removeprefix("ADP-")
        formal_path = proposal_path.with_name(f"ADP-{next_number:04d}-{slug}")
        if (batch / formal_path).exists():
            raise AdmissionError(f"formal decision already exists: {formal_path}")
        _git(batch, "mv", proposal, formal_path.as_posix())
        tracked = tuple(filter(None, _git(batch, "ls-files").splitlines()))
        old_name = proposal_path.name
        new_name = formal_path.name
        for relative in tracked:
            candidate = batch / relative
            if not candidate.is_file():
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rewritten = content.replace(proposal, formal_path.as_posix()).replace(
                old_name, new_name
            )
            if rewritten != content:
                candidate.write_text(rewritten, encoding="utf-8")
        _record_supersession(batch, formal_path)
        rewrites.append({"proposal": proposal, "formal": formal_path.as_posix()})
        next_number += 1
    _git(batch, "add", "-u")
    _git(
        batch,
        "commit",
        "-m",
        "signetum: allocate formal decision identities",
        "-m",
        f"Signetum-Decision-Base: {base}",
    )
    return rewrites


def admit(batch: Path, members: tuple[Path, ...]) -> dict[str, object]:
    """Admit named members into one batch, exclusively."""

    with _exclusive_batch(batch):
        return _admit_held(batch, members)


def _admit_held(batch: Path, members: tuple[Path, ...]) -> dict[str, object]:
    _require_no_merge(batch)
    _require_clean(batch)
    batch_branch = _branch(batch)
    record = read_record(_state_root(batch), batch_branch)
    if record.kind != "batch" or batch_branch == delivery_policy(batch).branch:
        raise AdmissionError(f"refusing batch admission outside a batch workspace: {batch_branch}")
    graph, _ = _runtime_validation(load_manifest(batch / "signetum.toml"))
    graph.gate("prepare")
    graph.gate("batch")

    admitted: list[dict[str, object]] = []
    unchanged: list[dict[str, str]] = []
    for raw_member in members:
        member = raw_member.resolve()
        if member == batch:
            raise AdmissionError("batch cannot admit itself")
        _require_clean(member)
        member_branch = _branch(member)
        member_tip = _git(member, "rev-parse", "HEAD")
        batch_tip = _git(batch, "rev-parse", "HEAD")
        member_manifest = load_manifest(member / "signetum.toml")
        member_graph, _ = _runtime_validation(member_manifest)
        member_graph.gate("prepare")
        member_graph.gate("batch")
        member_base = _recorded_base(member)
        try:
            carried = require_member_changes(
                member,
                member_manifest,
                member_base,
                member_tip,
                changes_naming_member(member, member_branch),
            )
            for change_id in member_scope(
                member, member_manifest, member_base, member_tip
            ).first_delivered:
                claim_change(_state_root(member), change_id, member_branch)
        except (ChangeError, DeviationError, WorkspaceError) as error:
            raise AdmissionError(str(error)) from error
        plans = delivered_plans(member, member_manifest, carried, member_tip)
        record = {"branch": member_branch, "original": member_tip, "worktree": str(member)}
        if _is_ancestor(batch, member_tip, batch_tip):
            unchanged.append(record)
            continue
        batch_base = _recorded_base(batch)
        ready_evidence = _admission_evidence(member, member_tip, member_manifest)
        patch_id = _stable_patch_id(member, batch_base, member_tip)
        message = "\n".join(
            (
                f"merge: admit {member_branch}",
                "",
                f"Signetum-Base: {batch_base}",
                f"Signetum-Original: {member_tip}",
                f"Signetum-Patch-ID: {patch_id}",
                f"Signetum-Ready-Evidence: {ready_evidence}",
                *(f"Signetum-Plan: {plan}" for plan in plans),
            )
        )
        git = _git_executable()
        completed = subprocess.run(  # nosec B603
            (
                git,
                "-C",
                str(batch),
                "merge",
                "--no-ff",
                member_tip,
                "-m",
                message,
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            merge_head = Path(_git(batch, "rev-parse", "--git-path", "MERGE_HEAD"))
            if not merge_head.is_absolute():
                merge_head = batch / merge_head
            diagnostic = completed.stderr.strip() or completed.stdout.strip()
            if merge_head.is_file():
                raise MergeConflict(
                    diagnostic or "batch has an open merge",
                    expected=f"resolve and stage paths, then batch-continue {batch}",
                )
            raise OperationFailed(diagnostic or "batch merge failed")
        admission_commit = _git(batch, "rev-parse", "HEAD")
        admitted.append(
            {
                **record,
                "patch_id": patch_id,
                "ready_evidence": ready_evidence,
                "plan": list(plans),
                "admission_commit": admission_commit,
            }
        )

    try:
        preparation = worktree_prepare(batch)
    except InfrastructureError as error:
        retry = ["batch-admit", str(batch)]
        for member in members:
            retry.extend(("--member", str(member)))
        raise InfrastructureError(str(error), expected=shlex.join(retry)) from error
    graph, _ = _runtime_validation(load_manifest(batch / "signetum.toml"))
    executed = {shard.digest for shard in graph.shards if shard.name in preparation["executed"]}
    static = run_diagnostic_gate(batch, graph, "batch", executed=executed, advisory_world=True)
    return {
        "schema_version": 1,
        "status": "admitted",
        "preparation": preparation,
        "static": static,
        "batch": str(batch),
        "batch_branch": batch_branch,
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
        "admitted": admitted,
        "unchanged": unchanged,
    }


def continue_batch(batch: Path) -> dict[str, object]:
    """Complete one batch's pending merge, exclusively."""

    with _exclusive_batch(batch):
        return _continue_batch_held(batch)


def _continue_batch_held(batch: Path) -> dict[str, object]:
    merge_head = Path(_git(batch, "rev-parse", "--git-path", "MERGE_HEAD"))
    if not merge_head.is_absolute():
        merge_head = batch / merge_head
    if not merge_head.is_file():
        raise AdmissionError("batch has no merge to continue")
    unmerged = _git(batch, "diff", "--name-only", "--diff-filter=U")
    if unmerged:
        raise AdmissionError(f"unresolved merge paths: {unmerged}")
    staged = _git(batch, "diff", "--cached", "--name-only")
    if not staged:
        raise AdmissionError("batch continuation has no staged resolution")
    preparation = worktree_prepare(batch, allow_merge=True)
    before = _git(batch, "rev-parse", "HEAD")
    staged_tree = _git(batch, "write-tree")
    other = _git(batch, "rev-parse", "MERGE_HEAD")
    against_first = set(_git(batch, "diff", "--name-only", before, staged_tree).splitlines())
    against_second = set(_git(batch, "diff", "--name-only", other, staged_tree).splitlines())
    repaired = tuple(sorted(against_first & against_second))
    manifest = load_manifest(batch / "signetum.toml")
    selected = select_paths(repaired, manifest)
    shards, _ = _member_shards(manifest, selected, member_closure=False)
    graph, _ = _runtime_validation(manifest, member_shards=shards)
    executed = {shard.digest for shard in graph.shards if shard.name in preparation["executed"]}
    repaired_checks = run_diagnostic_gate(batch, graph, "member", executed=executed)
    static = run_diagnostic_gate(batch, graph, "batch", executed=executed, advisory_world=True)
    if _git(batch, "rev-parse", "HEAD") != before or _git(batch, "write-tree") != staged_tree:
        raise ValidationExecutionError("validation changed staged merge identity")
    if run_git(batch, "diff", "--quiet").returncode:
        raise ValidationExecutionError("validation changed merge working files")
    git = _git_executable()
    completed = subprocess.run(  # nosec B603
        (git, "-C", str(batch), "commit", "--no-edit"),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AdmissionError(completed.stderr.strip() or completed.stdout.strip())
    committed = _git(batch, "rev-parse", "HEAD")
    batch_base = _recorded_base(batch)
    if batch_base is None:
        raise AdmissionError("continued admission has no approved batch base")
    return {
        "schema_version": 1,
        "status": "continued",
        "preparation": preparation,
        "repaired_paths": list(repaired),
        "checks": repaired_checks,
        "static": static,
        "batch": str(batch),
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
        "admission_commit": committed,
    }


def batch_open(repository: Path, members: tuple[Path, ...]) -> dict[str, object]:
    if not members:
        raise AdmissionError("batch-open requires explicitly named members")
    _, approved_base = fresh_delivery(repository)
    branch = f"batch/{approved_base}"
    opened = open_workspace(
        repository,
        branch,
        approved_base,
        kind="batch",
        members=tuple(str(member.resolve()) for member in members),
    )
    batch = Path(str(opened["worktree"]))
    result = admit(batch, members)
    return {**result, "status": "opened", "worktree": str(batch)}


def batch_deliver(
    source: Path, target: Path, expected_base: str, expected_tip: str
) -> dict[str, object]:
    _require_clean(source)
    _require_clean(target)
    if _git(source, "rev-parse", "HEAD") != expected_tip:
        raise AdmissionError("source tip differs from expected batch tip")
    target_head = _git(target, "rev-parse", "HEAD")
    recorded_base = _recorded_base(source)
    if recorded_base != expected_base:
        raise AdmissionError("recorded batch base differs from expected base")
    if _attested_base(source, expected_tip) != recorded_base:
        raise AdmissionError("batch provenance does not attest to the recorded base")
    final_receipts = sorted(_receipt_root(source).glob("final-*.json"))
    if not final_receipts:
        raise AdmissionError("no final receipt exists")
    matching_receipt = next(
        (
            path
            for path in final_receipts
            if (payload := json.loads(path.read_text(encoding="utf-8"))).get("source")
            == expected_tip
            and payload.get("base") == expected_base
            and payload.get("valid") is True
        ),
        None,
    )
    if matching_receipt is None:
        raise AdmissionError("final receipt does not bind the expected batch tip")

    target_branch = _branch(target)
    if target_branch != delivery_policy(source).branch:
        raise AdmissionError("target branch is not the repository-declared delivery branch")
    remote_before = _remote_branch_tip(target, target_branch)
    resumed_commit = None
    if remote_before != expected_base:
        _git(source, "fetch", "--no-tags", "origin", f"refs/heads/{target_branch}")
        parents = _git(source, "show", "-s", "--format=%P", remote_before).split()
        remote_tree = _git(source, "rev-parse", f"{remote_before}^{{tree}}")
        source_tree = _git(source, "rev-parse", f"{expected_tip}^{{tree}}")
        if parents != [expected_base, expected_tip] or remote_tree != source_tree:
            raise AdmissionError("remote delivery branch differs from expected base")
        resumed_commit = remote_before
    if target_head != expected_base and target_head != resumed_commit:
        raise AdmissionError("target tip differs from expected base or resumed delivery")

    members, plans = _delivery_provenance(source, expected_base, expected_tip)
    if not _is_ancestor(source, expected_base, expected_tip):
        raise AdmissionError("batch tip does not descend from expected base")
    if resumed_commit is None:
        delivery_commit = _git(
            source,
            "commit-tree",
            f"{expected_tip}^{{tree}}",
            "-p",
            expected_base,
            "-p",
            expected_tip,
            "-m",
            f"Merge validated batch {expected_tip}\n\nSignetum-Batch-Base: {expected_base}",
        )
        try:
            _git(source, "push", "origin", f"{delivery_commit}:refs/heads/{target_branch}")
        except AdmissionError as error:
            raise OperationFailed(
                str(error), expected="inspect the remote base and retry batch-deliver"
            ) from error
    else:
        delivery_commit = resumed_commit
    remote_after = _remote_branch_tip(target, target_branch)
    if remote_after != delivery_commit:
        raise AdmissionError("remote delivery confirmation differs from delivered commit")

    _git(target, "merge", "--ff-only", delivery_commit)
    removed_worktrees, retained_worktrees = _cleanup_delivered_worktrees(target, source, members)
    return {
        "schema_version": 1,
        "status": "delivered",
        "base": expected_base,
        "source": expected_tip,
        "target": str(target),
        "target_branch": target_branch,
        "delivery_commit": delivery_commit,
        "remote": remote_after,
        "members": members,
        "plans": plans,
        "validation": {"final_receipt": str(matching_receipt), "source": expected_tip},
        "removed_worktrees": removed_worktrees,
        "retained_worktrees": retained_worktrees,
    }


def _remote_branch_tip(repository: Path, branch: str) -> str:
    git = _git_executable()
    completed = subprocess.run(  # nosec B603
        (git, "-C", str(repository), "ls-remote", "--heads", "origin", branch),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AdmissionError(completed.stderr.strip() or "remote branch lookup failed")
    lines = tuple(line for line in completed.stdout.splitlines() if line.strip())
    if len(lines) != 1:
        raise AdmissionError(f"remote branch identity is not unique: {branch}")
    return lines[0].split()[0]


def _git_executable() -> str:
    executable = which("git")
    if executable is None:
        raise AdmissionError("git executable is unavailable")
    return executable


class OperationParser(argparse.ArgumentParser):
    """Keep invalid lifecycle invocations in the result contract."""

    def error(self, message: str) -> Never:
        raise AdmissionError(message, expected="inspect lifecycle --help and correct arguments")


def _parser() -> argparse.ArgumentParser:
    parser = OperationParser()
    commands = parser.add_subparsers(dest="command", required=True)
    workspace = commands.add_parser("workspace-open")
    workspace.add_argument("branch")
    workspace.add_argument("base")
    sync = commands.add_parser("workspace-sync")
    sync.add_argument("--batch", type=Path)
    prepare = commands.add_parser("worktree-prepare")
    prepare.add_argument("worktree", type=Path)
    clean = commands.add_parser("cleanup")
    clean.add_argument("--worktree", type=Path)
    clean.add_argument("--branch")
    clean.add_argument("--all-delivered", action="store_true")
    clean.add_argument("--protected-worktree", type=Path, action="append", default=[])
    clean.add_argument("--discard", action="store_true")
    discard = commands.add_parser("batch-discard")
    discard.add_argument("batch", type=Path)
    diagnostic = commands.add_parser("changed")
    diagnostic.add_argument("--explain", action="store_true")
    diagnostic.add_argument("--validate-only", action="store_true")
    commands.add_parser("ready")
    opening = commands.add_parser("batch-open")
    opening.add_argument("--member", type=Path, action="append", required=True)
    admission = commands.add_parser("batch-admit")
    admission.add_argument("--batch", type=Path, required=True)
    admission.add_argument("--member", type=Path, action="append", required=True)
    continuation = commands.add_parser("batch-continue")
    continuation.add_argument("--batch", type=Path, required=True)
    commands.add_parser("final")
    delivery = commands.add_parser("batch-deliver")
    delivery.add_argument("source", type=Path)
    delivery.add_argument("target", type=Path)
    delivery.add_argument("expected_base")
    delivery.add_argument("expected_batch_tip")
    return parser


def main(arguments: list[str] | None = None) -> int:
    supplied = sys.argv[1:] if arguments is None else arguments
    operation = supplied[0] if supplied else "lifecycle"
    repository = Path.cwd().resolve()
    try:
        parsed = _parser().parse_args(supplied)
        result: dict[str, object]
        if parsed.command == "workspace-open":
            result = workspace_open(repository, parsed.branch, parsed.base)
        elif parsed.command == "workspace-sync":
            result = workspace_sync(repository, parsed.batch.resolve() if parsed.batch else None)
        elif parsed.command == "worktree-prepare":
            result = dict(worktree_prepare(parsed.worktree.resolve()))
        elif parsed.command == "cleanup":
            result = cleanup(
                repository,
                worktree=parsed.worktree,
                branch=parsed.branch,
                all_delivered=parsed.all_delivered,
                discard=parsed.discard,
                protected_worktrees=tuple(parsed.protected_worktree),
            )
        elif parsed.command == "batch-discard":
            result = batch_discard(parsed.batch.resolve())
        elif parsed.command == "changed":
            result = changed(repository, parsed.explain, validate_only=parsed.validate_only)
        elif parsed.command == "ready":
            result = validate(repository, "member")
        elif parsed.command == "batch-open":
            result = batch_open(repository, tuple(parsed.member))
        elif parsed.command == "batch-admit":
            result = admit(parsed.batch.resolve(), tuple(parsed.member))
        elif parsed.command == "batch-continue":
            result = continue_batch(parsed.batch.resolve())
        elif parsed.command == "final":
            result = validate(repository, "final")
        else:
            result = batch_deliver(
                parsed.source.resolve(),
                parsed.target.resolve(),
                parsed.expected_base,
                parsed.expected_batch_tip,
            )
    except (
        OperationError,
        ManifestError,
        ValidationGraphError,
        ValidationExecutionError,
        WorkspaceError,
        GitError,
        OSError,
    ) as error:
        if isinstance(error, OperationError):
            status = error.status
            expected = error.expected
        elif isinstance(error, ValidationInfrastructureError):
            status = OperationStatus.INFRASTRUCTURE_ERROR
            expected = "restore the declared validation inputs and tools, then retry"
        elif isinstance(error, ValidationExecutionError):
            status = OperationStatus.FAILED
            expected = "repair the failing checks and retry the operation"
        elif isinstance(error, OSError):
            status = OperationStatus.INFRASTRUCTURE_ERROR
            expected = "restore the required executable or filesystem and retry"
        else:
            status = OperationStatus.INVALID
            expected = "correct the repository manifest and retry"
        log = _archive_operation_failure(repository, str(error))
        print(f"{operation}: {error}", file=sys.stderr)
        failure = OperationResult(operation, status, {}, str(error), expected, log)
        print(json.dumps(failure.document(), sort_keys=True))
        return EXIT_CODES[status]
    outcome = result.pop("status", "passed")
    document = OperationResult(
        operation, OperationStatus.PASSED, {**result, "outcome": outcome}
    ).document()
    print(json.dumps(document, sort_keys=True))
    return 0


def _archive_operation_failure(repository: Path, diagnostic: str) -> str | None:
    """Retain failure output under the shared machine-local state authority."""

    try:
        root = _state_root(repository) / "logs"
        root.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="operation-", suffix=".log", dir=root)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(diagnostic + "\n")
        return name
    except (OSError, OperationError):
        return None


if __name__ == "__main__":
    sys.exit(main())
