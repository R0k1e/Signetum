"""Lifecycle authority for explicit RepoSeal batch admission."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess  # nosec B404 -- fixed tuple commands, never a shell
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Literal

from reposeal.deviations import DeviationError, approval_view, reconciliation_summary
from reposeal.evidence.receipts import EvidenceReceipt, ReceiptError, ValidationSelection
from reposeal.impact import select_impact
from reposeal.manifest import ManifestError, RepositoryManifest, load_manifest
from reposeal.profiles import resolve_profiles
from reposeal.validation import (
    GateDeclaration,
    GraphContribution,
    ToolDeclaration,
    ValidationShard,
    command_digest,
    resolve_validation_graph,
)
from reposeal.validation.execution import (
    ValidationExecutionError,
    ValidationInputs,
    execute_gate,
)
from reposeal.validation.repository import ReceiptStore, RepositoryValidationAdapter
from reposeal.waivers import WaiverError, load_waivers
from reposeal.workspaces import WorkspaceError, WorkspaceRecord, read_record, write_record


class AdmissionError(ValueError):
    """The requested member cannot be admitted safely."""


@dataclass(frozen=True)
class WorkspaceIdentity:
    """One registered Worktrunk workspace identity."""

    branch: str
    path: Path
    head: str
    dirty: bool


def _mise_executable() -> str:
    executable = which("mise")
    if executable is None:
        raise AdmissionError(
            "Mise executable is unavailable; install Mise and run `mise install` in the repository"
        )
    return executable


def _run_tool(
    repository: Path, command: tuple[str, ...], *, capture_output: bool = True
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("GIT_") or name in {
            "PYTHONHOME",
            "PYTHONPATH",
            "UV_PROJECT_ENVIRONMENT",
            "VIRTUAL_ENV",
        }:
            environment.pop(name)
    environment["MISE_TRUSTED_CONFIG_PATHS"] = str(repository.resolve())
    completed = subprocess.run(  # nosec B603
        (_mise_executable(), "exec", "--", *command),
        cwd=repository,
        check=False,
        capture_output=capture_output,
        env=environment,
        text=True,
    )
    if completed.returncode != 0:
        diagnostic = (completed.stderr or "").strip() or (completed.stdout or "").strip()
        detail = diagnostic or f"Mise could not execute {command[0]}"
        raise AdmissionError(f"{detail}; run `mise install` in the repository")
    return completed


def _worktrunk(
    repository: Path, arguments: tuple[str, ...], *, json_output: bool = False
) -> object:
    command = (
        "wt",
        "-C",
        str(repository),
        "--yes",
        "--config-set",
        "list.json-schema=2",
        *arguments,
    )
    completed = _run_tool(repository, command)
    if not json_output:
        return completed.stdout
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AdmissionError(f"invalid Worktrunk JSON: {error.msg}") from error


def _worktrees(repository: Path) -> tuple[WorkspaceIdentity, ...]:
    payload = _worktrunk(repository, ("list", "--format=json"), json_output=True)
    if not isinstance(payload, dict) or payload.get("schema") != 2:
        raise AdmissionError("invalid Worktrunk JSON: expected schema 2 envelope")
    items = payload.get("items")
    if not isinstance(items, list):
        raise AdmissionError("invalid Worktrunk JSON: items must be a list")
    result: list[WorkspaceIdentity] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("worktree"), dict):
            continue
        branch = item.get("branch")
        head = item.get("head")
        worktree = item["worktree"]
        changes = worktree.get("changes")
        if (
            not isinstance(branch, str)
            or not isinstance(head, dict)
            or not isinstance(head.get("sha"), str)
            or not isinstance(worktree.get("path"), str)
            or not isinstance(changes, dict)
        ):
            raise AdmissionError("invalid Worktrunk JSON: incomplete registered workspace identity")
        dirty = any(
            changes.get(name) is True
            for name in ("staged", "modified", "untracked", "renamed", "deleted", "conflicted")
        )
        result.append(
            WorkspaceIdentity(branch, Path(worktree["path"]).resolve(), head["sha"], dirty)
        )
    return tuple(result)


def _registered_workspace(repository: Path, branch: str) -> WorkspaceIdentity:
    matches = tuple(workspace for workspace in _worktrees(repository) if workspace.branch == branch)
    if len(matches) != 1:
        raise AdmissionError(f"Worktrunk did not report one registered workspace for {branch}")
    return matches[0]


def _state_root(repository: Path) -> Path:
    common = Path(_git(repository, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repository / common
    root = common.resolve() / "reposeal"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _recorded_base(repository: Path, branch: str | None = None) -> str:
    """Return the base this workspace was cut from.

    The record is the only authority. A base is never re-derived from commit
    prose, and never accepted from a caller who could name a different one.
    """

    resolved = branch if branch is not None else _branch(repository)
    try:
        return read_record(_state_root(repository), resolved).base
    except WorkspaceError as error:
        raise AdmissionError(str(error)) from error


def _receipt_root(repository: Path) -> Path:
    root = _state_root(repository) / "validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _runtime_validation(
    manifest: RepositoryManifest, *, member_shards: tuple[str, ...] | None = None
):
    resolved = resolve_profiles(
        manifest.profiles.enabled, replacements=manifest.profiles.replacements
    )
    shards = [
        ValidationShard(
            item.name, item.command, item.requires, item.evidence, item.findings_command
        )
        for item in manifest.validation.shards
    ]
    gates = [GateDeclaration(item.name, item.shards) for item in manifest.validation.gates]
    if member_shards is not None:
        gates = [item for item in gates if item.name != "member"]
        gates.append(GateDeclaration("member", member_shards))
    graph = resolve_validation_graph(
        (GraphContribution("repository", tuple(shards), tuple(gates)),)
    )
    inputs = ValidationInputs(
        "reposeal.toml",
        tuple(sorted(profile.identity for profile in resolved)),
        tuple(sorted(manifest.repository.lockfiles)),
        tuple(
            ToolDeclaration(item.name, item.identity_command) for item in manifest.validation.tools
        ),
    )
    return graph, inputs


def _selection(repository: Path, base: str, manifest: RepositoryManifest) -> ValidationSelection:
    files = tuple(
        filter(None, _git(repository, "diff", "--name-only", f"{base}...HEAD").splitlines())
    )
    impact = select_impact(files, manifest.impact.rules)
    encoded = json.dumps(files, separators=(",", ":")).encode()
    modified_tests = tuple(
        path
        for path in files
        if path.startswith("tests/") or "/tests/" in path or Path(path).name.startswith("test_")
    )
    reasons = tuple(f"impact rule {name} matched" for name in impact.rules)
    return ValidationSelection(
        changed_paths_digest="sha256:" + hashlib.sha256(encoded).hexdigest(),
        rules=impact.rules,
        profiles=impact.profiles,
        gates=impact.gates,
        shards=impact.shards,
        modified_tests=modified_tests,
        external_obligations=(),
        unexplained=impact.unexplained,
        requires_final=impact.requires_final,
        reasons=reasons,
    )


def _member_shards(
    manifest: RepositoryManifest, selection: ValidationSelection
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the member shards to execute and the world shards left to final.

    Member closure stays a function of the observed tree, so a world shard
    reached through an impact rule or a composed gate is deferred rather than
    allowed to make an unrelated member unclosable.
    """

    gate_shards = {gate.name: gate.shards for gate in manifest.validation.gates}
    world = {item.name for item in manifest.validation.shards if item.evidence == "world"}
    selected: list[str] = list(manifest.validation.member_required)
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
    if selection.unexplained:
        for shard in gate_shards["member"]:
            admit(shard)
    return tuple(selected), tuple(sorted(deferred))


def workspace_open(repository: Path, branch: str, base: str) -> dict[str, object]:
    root = Path(_git(repository, "rev-parse", "--show-toplevel"))
    source = _git(root, "rev-parse", base)
    _worktrunk(
        root,
        (
            "switch",
            "--create",
            branch,
            "--base",
            base,
            "--no-hooks",
            "--no-cd",
            "--format=json",
        ),
        json_output=True,
    )
    workspace = _registered_workspace(root, branch)
    if workspace.head != source:
        raise AdmissionError("Worktrunk workspace does not match the exact approved base")
    _record_workspace(root, branch, source, "member")
    return {
        "schema_version": 1,
        "status": "opened",
        "branch": branch,
        "base": source,
        "source": source,
        "worktree": str(workspace.path),
    }


def _record_workspace(
    repository: Path,
    branch: str,
    base: str,
    kind: Literal["member", "batch"],
    members: tuple[str, ...] = (),
) -> None:
    try:
        write_record(
            _state_root(repository),
            WorkspaceRecord(schema_version=1, branch=branch, base=base, kind=kind, members=members),
        )
    except WorkspaceError as error:
        raise AdmissionError(str(error)) from error


def changed(repository: Path, explain: bool) -> dict[str, object]:
    base = _recorded_base(repository)
    manifest = load_manifest(repository / "reposeal.toml")
    selected = _selection(repository, base, manifest)
    files = tuple(
        filter(None, _git(repository, "diff", "--name-only", f"{base}...HEAD").splitlines())
    )
    return {
        "schema_version": 1,
        "status": "changed",
        "base": base,
        "source": _git(repository, "rev-parse", "HEAD"),
        "files": files,
        "selection": json.loads(json.dumps(selected.__dict__)),
        "rules": selected.rules,
        "profiles": selected.profiles,
        "gates": selected.gates,
        "shards": selected.shards,
        "unexplained": selected.unexplained,
        "requires_final": selected.requires_final,
        "explain": explain,
    }


def validate(repository: Path, kind: str) -> dict[str, object]:
    _require_clean(repository)
    source = _git(repository, "rev-parse", "HEAD")
    base = None if kind == "final" else _recorded_base(repository)
    if base is not None and source == _git(repository, "rev-parse", base):
        raise AdmissionError("source has no commits beyond the approved base")
    evidence_base = _recorded_base(repository) if kind == "final" else None
    if kind == "final":
        proposals = _proposal_paths(repository)
        if proposals:
            raise AdmissionError(f"final refuses proposal decisions: {', '.join(proposals)}")
        _require_numbering_base(repository, evidence_base, source)
        # A batch whose tip is still its base admitted nothing, so it carries
        # no Change identity to reconcile.
        if evidence_base is None or evidence_base == source:
            change_ids: tuple[str, ...] = ()
        else:
            _, plans = _delivery_provenance(repository, evidence_base, source)
            change_ids = _change_ids_from_plans(tuple(plans))
        try:
            reconciliation = reconciliation_summary(repository, change_ids)
            approvals = [approval_view(repository, change_id) for change_id in change_ids]
        except DeviationError as error:
            raise AdmissionError(f"deviation reconciliation failed: {error}") from error
    else:
        reconciliation = None
        approvals = None
    manifest = load_manifest(repository / "reposeal.toml")
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
        schema_digest=manifest.reposeal.evidence_schema_digest,
        waivers=waivers,
    )
    adapter = RepositoryValidationAdapter(repository)
    receipt = execute_gate(graph, gate, inputs, adapter)
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
    if reconciliation is not None and approvals is not None:
        payload["delivery_review"] = {
            "approvals": approvals,
            "reconciliation": reconciliation,
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
    git = _git_executable()
    completed = subprocess.run(  # nosec B603
        (git, "-C", str(repository), *arguments),
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        raise AdmissionError(diagnostic or f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()


def _require_clean(worktree: Path) -> None:
    status = _git(worktree, "status", "--porcelain")
    if status:
        raise AdmissionError(f"worktree is not clean: {worktree}")


def _branch(worktree: Path) -> str:
    branch = _git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        raise AdmissionError(f"member has no branch: {worktree}")
    return branch


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


def _commit_plans(repository: Path, commit: str) -> tuple[str, ...]:
    body = _git(repository, "show", "-s", "--format=%B", commit)
    return tuple(
        sorted(
            {
                item.strip()
                for declared in re.findall(r"^Delivers:\s*(.+)$", body, re.MULTILINE)
                for item in declared.split(",")
                if item.strip()
            }
        )
    )


def _change_ids_from_plans(plans: tuple[str, ...]) -> tuple[str, ...]:
    change_ids: set[str] = set()
    for plan in plans:
        path = Path(plan)
        if len(path.parts) < 4 or path.parts[0] != "changes" or path.parts[2] != "plans":
            raise AdmissionError(f"Plan is outside one active Change: {plan}")
        change_ids.add(path.parts[1])
    if not change_ids:
        raise AdmissionError("batch carries no active Change identity")
    return tuple(sorted(change_ids))


def _admission_evidence(member: Path, tip: str, manifest: RepositoryManifest) -> str:
    """Locate evidence proving what this member's own selection requires.

    Evidence is matched by observed tree and by shard command digest, never by
    commit identity, receipt gate, or shard name: an amended trailer, an
    equivalent rebase, a renamed shard, and a completed final gate all prove
    the same work.
    """

    selection = _selection(member, _recorded_base(member), manifest)
    required_names, _ = _member_shards(manifest, selection)
    declared = {item.name: item.command for item in manifest.validation.shards}
    required = frozenset(command_digest(declared[name]) for name in required_names)
    tree = _git(member, "rev-parse", f"{tip}^{{tree}}")
    for path in sorted(_receipt_root(member).glob("*-lifecycle-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            receipt = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ReceiptError):
            continue
        if receipt.identity.tree != tree or not receipt.valid:
            continue
        if required <= receipt.execution.command_digests:
            return path.name
    if selection.requires_final:
        return "deferred:requires-final:" + (",".join(selection.rules) or "unexplained")
    raise AdmissionError(
        "member has no evidence proving its selected validation for the exact tree"
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
    return tuple(
        line for line in _git(repository, "ls-files", "*ADP-proposal-*.md").splitlines() if line
    )


def _attested_base(repository: Path, tip: str) -> str | None:
    """Read the base a batch's provenance commit attests to.

    This is the durable attestation, not the authority: operations read the
    workspace record. Delivery compares the two so a record which disagrees
    with committed history cannot land.
    """

    history = _git(repository, "log", "--first-parent", "--format=%B%x00", tip)
    marker = re.search(r"^RepoSeal-Batch-Base:\s*(\S+)$", history, re.MULTILINE)
    return marker.group(1) if marker else None


def _require_numbering_base(repository: Path, base: str | None, tip: str) -> None:
    if base is None:
        return
    messages = _git(repository, "log", "--first-parent", "--format=%B%x00", f"{base}..{tip}")
    numbering_bases = re.findall(r"^RepoSeal-Decision-Base:\s*(\S+)$", messages, re.MULTILINE)
    if numbering_bases and set(numbering_bases) != {base}:
        raise AdmissionError("decision numbering is bound to a different delivery base")


def _number_proposals(batch: Path, base: str) -> list[dict[str, str]]:
    proposals = _proposal_paths(batch)
    if not proposals:
        return []
    base_names = _git(batch, "ls-tree", "-r", "--name-only", base).splitlines()
    used = [
        int(match.group(1))
        for path in (*base_names, *_git(batch, "ls-files").splitlines())
        if (match := re.search(r"(?:^|/)ADP-(\d{4})-[^/]+\.md$", path))
    ]
    next_number = max(used, default=0) + 1
    rewrites: list[dict[str, str]] = []
    for proposal in sorted(proposals):
        proposal_path = Path(proposal)
        slug = proposal_path.name.removeprefix("ADP-proposal-")
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
        rewrites.append({"proposal": proposal, "formal": formal_path.as_posix()})
        next_number += 1
    _git(batch, "add", "-u")
    _git(
        batch,
        "commit",
        "-m",
        "reposeal: allocate formal decision identities",
        "-m",
        f"RepoSeal-Decision-Base: {base}",
    )
    return rewrites


def admit(batch: Path, members: tuple[Path, ...]) -> dict[str, object]:
    _require_clean(batch)
    batch_branch = _branch(batch)
    if batch_branch in {"main", "master", "product"}:
        raise AdmissionError(f"refusing batch admission on delivery branch: {batch_branch}")

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
        plans = _commit_plans(member, member_tip)
        if not plans:
            raise AdmissionError("member commit has no Delivers Plan trailer")
        record = {"branch": member_branch, "original": member_tip, "worktree": str(member)}
        if _is_ancestor(batch, member_tip, batch_tip):
            unchanged.append(record)
            continue
        batch_base = _recorded_base(batch)
        ready_evidence = _admission_evidence(
            member, member_tip, load_manifest(member / "reposeal.toml")
        )
        patch_id = _stable_patch_id(member, batch_base, member_tip)
        message = "\n".join(
            (
                f"merge: admit {member_branch}",
                "",
                f"RepoSeal-Base: {batch_base}",
                f"RepoSeal-Original: {member_tip}",
                f"RepoSeal-Patch-ID: {patch_id}",
                f"RepoSeal-Ready-Evidence: {ready_evidence}",
                *(f"RepoSeal-Plan: {plan}" for plan in plans),
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
            result = {
                "schema_version": 1,
                "status": "conflict",
                "batch": str(batch),
                "member": record,
                "diagnostic": completed.stderr.strip() or completed.stdout.strip(),
            }
            print(json.dumps(result, sort_keys=True))
            raise SystemExit(3)
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

    decisions = _number_proposals(batch, _recorded_base(batch))
    return {
        "schema_version": 1,
        "status": "admitted",
        "batch": str(batch),
        "batch_branch": batch_branch,
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
        "admitted": admitted,
        "unchanged": unchanged,
        "decisions": decisions,
    }


def continue_batch(batch: Path) -> dict[str, object]:
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
    decisions = _number_proposals(batch, batch_base)
    return {
        "schema_version": 1,
        "status": "continued",
        "batch": str(batch),
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
        "admission_commit": committed,
        "decisions": decisions,
    }


def batch_open(repository: Path, members: tuple[Path, ...]) -> dict[str, object]:
    _require_clean(repository)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    branch = f"batch/{stamp}"
    approved_base = _git(repository, "rev-parse", "HEAD")
    opened = workspace_open(repository, branch, "HEAD")
    batch = Path(str(opened["worktree"]))
    # A batch is a workspace which declares members, so it carries the same
    # record a member does and its base is read the same way.
    _record_workspace(
        repository,
        branch,
        approved_base,
        "batch",
        tuple(str(member.resolve()) for member in members),
    )
    _git(
        batch,
        "commit",
        "--allow-empty",
        "-m",
        "reposeal: open provenance batch",
        "-m",
        f"RepoSeal-Batch-Format: 1\nRepoSeal-Batch-Base: {approved_base}",
    )
    result = admit(batch, members)
    return {**result, "status": "opened", "worktree": str(batch)}


def batch_deliver(
    source: Path, target: Path, expected_base: str, expected_tip: str
) -> dict[str, object]:
    _require_clean(source)
    _require_clean(target)
    if _git(source, "rev-parse", "HEAD") != expected_tip:
        raise AdmissionError("source tip differs from expected batch tip")
    if _git(target, "rev-parse", "HEAD") != expected_base:
        raise AdmissionError("target tip differs from expected base")
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
    remote_before = _remote_branch_tip(target, target_branch)
    if remote_before != expected_base:
        raise AdmissionError("remote delivery branch differs from expected base")

    members, plans = _delivery_provenance(source, expected_base, expected_tip)
    _git(target, "merge", "--ff-only", expected_tip)
    delivery_commit = _git(target, "rev-parse", "HEAD")
    _git(target, "push", "origin", f"HEAD:refs/heads/{target_branch}")
    remote_after = _remote_branch_tip(target, target_branch)
    if remote_after != delivery_commit:
        raise AdmissionError("remote delivery confirmation differs from delivered commit")

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


def _delivery_provenance(
    repository: Path, expected_base: str, expected_tip: str
) -> tuple[list[dict[str, str]], list[str]]:
    merge_commits = tuple(
        filter(
            None,
            _git(
                repository,
                "rev-list",
                "--reverse",
                "--first-parent",
                "--merges",
                f"{expected_base}..{expected_tip}",
            ).splitlines(),
        )
    )
    members: list[dict[str, str]] = []
    plans: set[str] = set()
    for merge_commit in merge_commits:
        parents = _git(repository, "show", "-s", "--format=%P", merge_commit).split()
        if len(parents) != 2:
            raise AdmissionError("batch contains a merge without exactly one admitted member")
        subject = _git(repository, "show", "-s", "--format=%s", merge_commit)
        prefix = "merge: admit "
        if not subject.startswith(prefix):
            raise AdmissionError("batch contains an unrecognized merge authority")
        original = parents[1]
        body = _git(repository, "show", "-s", "--format=%B", merge_commit)
        fields = {
            key: value
            for key, value in re.findall(r"^RepoSeal-([^:]+):\s*(.+)$", body, re.MULTILINE)
        }
        if fields.get("Original") != original:
            raise AdmissionError("admission provenance original does not match merge parent")
        summary = _git(repository, "show", "-s", "--format=%s", original)
        member_plans = re.findall(r"^RepoSeal-Plan:\s*(.+)$", body, re.MULTILINE)
        plans.update(member_plans)
        members.append(
            {
                "branch": subject.removeprefix(prefix),
                "original": original,
                "patch_id": fields.get("Patch-ID", ""),
                "ready_evidence": fields.get("Ready-Evidence", ""),
                "plan": ",".join(member_plans),
                "admission_commit": merge_commit,
                "summary": summary,
            }
        )
    if not members:
        raise AdmissionError("batch contains no admitted member provenance")
    return members, sorted(plans)


def _remove_workspace(repository: Path, workspace: WorkspaceIdentity) -> None:
    _worktrunk(repository, ("remove", str(workspace.path)))


def _cleanup_delivered_worktrees(
    target: Path, source: Path, members: list[dict[str, str]]
) -> tuple[list[str], list[dict[str, str]]]:
    worktrees = {workspace.branch: workspace for workspace in _worktrees(target)}
    removed: list[str] = []
    retained: list[dict[str, str]] = []
    latest_members = {member["branch"]: member for member in members}
    for branch, member in latest_members.items():
        workspace = worktrees.get(branch)
        if workspace is None:
            continue
        if workspace.dirty:
            retained.append({"branch": branch, "worktree": str(workspace.path), "reason": "dirty"})
            continue
        if workspace.head != member["original"]:
            retained.append(
                {"branch": branch, "worktree": str(workspace.path), "reason": "advanced"}
            )
            continue
        _remove_workspace(target, workspace)
        removed.append(str(workspace.path))

    source_path = source.resolve()
    source_matches = tuple(
        workspace for workspace in worktrees.values() if workspace.path == source_path
    )
    if len(source_matches) != 1:
        raise AdmissionError("batch source is not one registered Worktrunk workspace")
    source_workspace = source_matches[0]
    if source_workspace.dirty:
        raise AdmissionError("batch source became dirty before Worktrunk removal")
    _remove_workspace(target, source_workspace)
    removed.append(str(source_workspace.path))
    return removed, retained


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    workspace = commands.add_parser("workspace-open")
    workspace.add_argument("branch")
    workspace.add_argument("base")
    diagnostic = commands.add_parser("changed")
    diagnostic.add_argument("--explain", action="store_true")
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
    parsed = _parser().parse_args(arguments)
    try:
        repository = Path.cwd().resolve()
        if parsed.command == "workspace-open":
            result = workspace_open(repository, parsed.branch, parsed.base)
        elif parsed.command == "changed":
            result = changed(repository, parsed.explain)
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
    except (AdmissionError, ManifestError, ValidationExecutionError) as error:
        # A refused operation is still one JSON result on stdout, never a
        # traceback: a failing gate is an ordinary outcome of the contract.
        print(
            json.dumps(
                {"schema_version": 1, "status": "refused", "reason": str(error)},
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
