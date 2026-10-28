"""Self-contained lifecycle authority for explicit Signetum batch delivery."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec B404 -- fixed tuple commands, never a shell
import sys
import tempfile
import tomllib
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime import resources
from _signetum_runtime.evidence_receipts import EvidenceReceipt, ReceiptError, ValidationSelection
from _signetum_runtime.execution import (
    ShardExecution,
    ValidationExecutionError,
    ValidationInfrastructureError,
    ValidationInputs,
    execute_gate,
)
from _signetum_runtime.findings import Finding, FindingsError, parse_findings
from _signetum_runtime.git import git_output as _git
from _signetum_runtime.impact import select_paths
from _signetum_runtime.inheritance import find_test_inheritance
from _signetum_runtime.operations import AdmissionError
from _signetum_runtime.process import run_command
from _signetum_runtime.receipt_store import ReceiptStore
from _signetum_runtime.recovery import shard_execution, with_recovery_history
from _signetum_runtime.validation import (
    GateDeclaration,
    ToolDeclaration,
    ValidationConfiguration,
    ValidationGraphError,
    ValidationShard,
    command_digest,
    resolve_validation_graph,
)
from _signetum_runtime.waivers import Waiver, WaiverError, load_waivers
from _signetum_runtime.workspaces import (
    WorkspaceError,
    WorkspaceRecord,
    read_record,
    record_path,
    write_record,
)
from _signetum_runtime.workspaces import (
    branch_name as _branch,
)
from _signetum_runtime.workspaces import (
    require_clean as _require_clean,
)
from _signetum_runtime.workspaces import (
    state_root as _state_root,
)
from deviations import DeviationError, approval_view, reconciliation_summary


@dataclass(frozen=True)
class WorkspaceIdentity:
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
    repository: Path,
    command: tuple[str, ...],
    *,
    required: bool = True,
    timeout_seconds: float = 1800,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ if environment is None else environment)
    for name in tuple(environment):
        if name.startswith("GIT_") or name in {
            "PYTHONHOME",
            "PYTHONPATH",
            "UV_PROJECT_ENVIRONMENT",
            "VIRTUAL_ENV",
        }:
            environment.pop(name)
    environment["MISE_TRUSTED_CONFIG_PATHS"] = str(repository.resolve())
    try:
        completed = run_command(
            repository,
            (_mise_executable(), "exec", "--", *command),
            timeout_seconds=timeout_seconds,
            environment=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        if required:
            raise AdmissionError(f"command could not complete: {command[0]}: {error}") from error
        raise
    if not required:
        return completed
    if completed.returncode != 0:
        diagnostic = (completed.stderr or "").strip() or (completed.stdout or "").strip()
        detail = diagnostic or f"Mise could not execute {command[0]}"
        raise AdmissionError(f"{detail}; run `mise install` in the repository")
    return completed


def _worktrunk(
    repository: Path, arguments: tuple[str, ...], *, json_output: bool = False
) -> object:
    completed = _run_tool(
        repository,
        (
            "wt",
            "-C",
            str(repository),
            "--yes",
            "--config-set",
            "list.json-schema=2",
            *arguments,
        ),
    )
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
        branch, head, worktree = item.get("branch"), item.get("head"), item["worktree"]
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


def _receipt_root(repository: Path) -> Path:
    root = _state_root(repository) / "validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _record_path(repository: Path, branch: str) -> Path:
    return record_path(_state_root(repository), branch)


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


def _read_record(repository: Path, branch: str) -> dict[str, object]:
    try:
        return asdict(read_record(_state_root(repository), branch))
    except WorkspaceError as error:
        raise AdmissionError(str(error)) from error


def _recorded_base(repository: Path, branch: str | None = None) -> str:
    """Return the base this workspace was cut from; the record is the authority."""

    resolved = branch if branch is not None else _branch(repository)
    return str(_read_record(repository, resolved)["base"])


def _write_receipt(repository: Path, kind: str, payload: dict[str, object]) -> Path:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    evidence = EvidenceReceipt.from_json(json.dumps(payload["evidence"]))
    raw = ReceiptStore(_receipt_root(repository)).write(kind, evidence)
    target = raw.with_name(raw.name.replace(f"{kind}-", f"{kind}-lifecycle-", 1))
    target.write_text(encoded, encoding="utf-8")
    return target


def _manifest(repository: Path) -> dict[str, object]:
    manifest = repository / "signetum.toml"
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        if data.get("schema_version") != 2:
            raise AdmissionError("unsupported signetum.toml schema")
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise AdmissionError(f"invalid validation authority: {error}") from error
    return data


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AdmissionError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise AdmissionError(f"{label} must be an array")
    return value


def _strings(value: object, label: str) -> list[str]:
    raw = _array(value, label)
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise AdmissionError(f"{label} must contain strings")
        result.append(item)
    return result


def _load_waivers(repository: Path) -> tuple[Waiver, ...]:
    try:
        return load_waivers(repository)
    except WaiverError as error:
        raise AdmissionError(str(error)) from error


def _member_shards(
    manifest: dict[str, object], selection: dict[str, object]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the member shards to execute and the world shards left to final.

    Member closure stays a function of the observed tree, so a world shard
    reached through an impact rule or a composed gate is deferred rather than
    allowed to make an unrelated member unclosable.
    """

    validation = _mapping(manifest.get("validation"), "validation")
    raw_shards = validation["shards"]
    if not isinstance(raw_shards, list):
        raise AdmissionError("validation.shards must be an array")
    world = {
        str(shard["name"])
        for item in raw_shards
        for shard in (_mapping(item, "validation shard"),)
        if shard.get("evidence", "tree") == "world"
    }
    raw_gates = validation["gates"]
    if not isinstance(raw_gates, list):
        raise AdmissionError("validation.gates must be an array")
    gates = {
        str(gate["name"]): _strings(gate["shards"], "gate.shards")
        for item in raw_gates
        for gate in (_mapping(item, "validation gate"),)
    }
    selected = _strings(validation.get("member_required", []), "member_required")
    deferred: list[str] = []

    def admit(name: str) -> None:
        if name in world:
            if name not in deferred:
                deferred.append(name)
        elif name not in selected:
            selected.append(name)

    for name in _strings(selection["shards"], "selection.shards"):
        admit(name)
    for name in _strings(selection["gates"], "selection.gates"):
        for shard_name in gates.get(name, ()):
            admit(shard_name)
    if selection["unexplained"]:
        for shard_name in gates["member"]:
            admit(shard_name)
    return tuple(selected), tuple(sorted(deferred))


class _ValidationAdapter:
    """Repository effects for the shared execution and evidence contracts."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()

    def commit_identity(self) -> str:
        return _git(self.repository, "rev-parse", "HEAD")

    def tree_identity(self) -> str:
        return _git(self.repository, "rev-parse", "HEAD^{tree}")

    def read_file(self, path: str) -> bytes:
        candidate = (self.repository / path).resolve()
        if not candidate.is_relative_to(self.repository):
            raise ValidationExecutionError(f"file escapes repository: {path}")
        try:
            return candidate.read_bytes()
        except OSError as error:
            raise ValidationInfrastructureError(f"validation input unavailable: {path}") from error

    def identify_tool(self, tool: ToolDeclaration) -> str:
        try:
            completed = self._run(tool.identity_command, timeout_seconds=60)
        except subprocess.TimeoutExpired as error:
            raise ValidationInfrastructureError(f"tool identity timed out: {tool.name}") from error
        identity = completed.stdout.strip()
        if completed.returncode or not identity:
            raise ValidationInfrastructureError(f"tool identity unavailable: {tool.name}")
        return identity

    def _run(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return _run_tool(
                self.repository,
                command,
                required=False,
                timeout_seconds=timeout_seconds,
                environment=environment,
            )
        except (OSError, AdmissionError) as error:
            raise ValidationInfrastructureError(str(error)) from error

    def run_shard(self, shard: ValidationShard) -> ShardExecution:
        allocation = (
            resources.allocate_workers(
                shard.workers, shard.worker_memory_mb, resources.observe_resources()
            )
            if shard.workers
            else {"workers": 0, "declared_workers": 0}
        )
        with tempfile.TemporaryDirectory(prefix="signetum-recovery-") as scratch:
            report = Path(scratch) / "recovered.json"
            try:
                completed = self._run(
                    shard.command,
                    timeout_seconds=shard.timeout_seconds,
                    environment=dict(
                        os.environ,
                        SIGNETUM_RECOVERY_REPORT=str(report),
                        SIGNETUM_VALIDATION_WORKERS=str(allocation["workers"]),
                    ),
                )
            except subprocess.TimeoutExpired:
                execution = ShardExecution(
                    False, f"{shard.name} did not return within {shard.timeout_seconds}s"
                )
            else:
                execution = shard_execution(shard.name, completed, report)
        return replace(execution, details={**execution.details, "resource_allocation": allocation})

    def report_findings(self, shard: ValidationShard) -> tuple[Finding, ...]:
        try:
            completed = self._run(shard.findings_command, timeout_seconds=60)
        except subprocess.TimeoutExpired as error:
            raise ValidationInfrastructureError(
                f"findings command timed out: {shard.name}"
            ) from error
        try:
            return parse_findings(completed.stdout)
        except FindingsError as error:
            raise ValidationExecutionError(str(error)) from error


def _run_gate(
    repository: Path,
    kind: str,
    selected_shards: tuple[str, ...] | None = None,
    *,
    base: str | None = None,
    selection: dict[str, object] | None = None,
) -> EvidenceReceipt:
    """Execute through the canonical graph, failure and evidence authorities."""

    data = _manifest(repository)
    validation = _mapping(data.get("validation"), "validation")
    try:
        configuration = ValidationConfiguration.from_mapping("repository", validation)
        contribution = configuration.contribution
        graph = resolve_validation_graph((contribution,))
        graph.gate(kind)
        if selected_shards is not None:
            gates = tuple(gate for gate in contribution.gates if gate.name != kind)
            contribution = replace(
                contribution, gates=(*gates, GateDeclaration(kind, selected_shards))
            )
            graph = resolve_validation_graph((contribution,))
        profiles = _mapping(data.get("profiles", {}), "profiles")
        repository_config = _mapping(data.get("repository"), "repository")
        identity = _mapping(data.get("signetum"), "signetum")
        schema = identity.get("evidence_schema_digest")
        if not isinstance(schema, str):
            raise AdmissionError("evidence schema digest is unavailable")
        if identity.get("evidence_protocol") != "reposeal.validation-evidence@3":
            raise AdmissionError("unsupported evidence protocol")
        selected = ValidationSelection.from_mapping(selection) if selection is not None else None

        def recovery_setting(name: str, default: int) -> int:
            value = validation.get(name, default)
            if type(value) is not int or value < 1:
                raise AdmissionError(f"validation.{name} must be a positive integer")
            return value

        inputs = ValidationInputs(
            configuration_path="signetum.toml",
            profiles=tuple(sorted(_strings(profiles.get("enabled", []), "profiles.enabled"))),
            lockfiles=tuple(
                sorted(_strings(repository_config.get("lockfiles", []), "repository.lockfiles"))
            ),
            tools=configuration.tools,
            base=base,
            selection=selected,
            schema_digest=schema,
            waivers=_load_waivers(repository),
            recovery_threshold=recovery_setting("recovery_threshold", 3),
            recovery_window=recovery_setting("recovery_window", 20),
        )
        inputs = with_recovery_history(inputs, _receipt_root(repository))
        adapter = _ValidationAdapter(repository)
        inherited = (
            find_test_inheritance(
                repository, _impact_rules(data), graph, inputs, adapter, _receipt_root(repository)
            )
            if kind == "member"
            and base is not None
            and any(shard.inherit for shard in graph.shards)
            else None
        )
        receipt = execute_gate(graph, kind, inputs, adapter, inherited=inherited)
        _require_clean(repository)
        return receipt
    except (ValidationGraphError, ValidationExecutionError, ReceiptError) as error:
        raise AdmissionError(str(error)) from error


def workspace_open(repository: Path, branch: str, base: str) -> dict[str, object]:
    return _open_workspace(repository, branch, base, kind="member", members=())


def _open_workspace(
    repository: Path,
    branch: str,
    base: str,
    *,
    kind: Literal["member", "batch"],
    members: tuple[str, ...],
) -> dict[str, object]:
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
    _record_workspace(root, branch, source, kind, members)
    return {
        "schema_version": 1,
        "status": "opened",
        "branch": branch,
        "base": source,
        "source": source,
        "worktree": str(workspace.path),
    }


@dataclass(frozen=True)
class _ImpactRule:
    """Normalized input for the shared selector; the manifest owns its fields."""

    name: str
    paths: tuple[str, ...]
    profiles: tuple[str, ...]
    gates: tuple[str, ...]
    shards: tuple[str, ...]
    requires_final: bool

    @classmethod
    def from_mapping(cls, rule: dict[str, object]) -> _ImpactRule:
        name = rule.get("name")
        if not isinstance(name, str):
            raise AdmissionError("impact rule name must be a string")
        return cls(
            name=name,
            paths=tuple(_strings(rule.get("paths", []), "impact.paths")),
            profiles=tuple(_strings(rule.get("profiles", []), "impact.profiles")),
            gates=tuple(_strings(rule.get("gates", []), "impact.gates")),
            shards=tuple(_strings(rule.get("shards", []), "impact.shards")),
            requires_final=rule.get("requires_final") is True,
        )


def _impact_rules(manifest: dict[str, object]) -> tuple[_ImpactRule, ...]:
    impact = _mapping(manifest.get("impact"), "impact")
    rules = (_mapping(item, "impact rule") for item in _array(impact["rules"], "impact.rules"))
    return tuple(_ImpactRule.from_mapping(rule) for rule in rules)


def changed(repository: Path, explain: bool) -> dict[str, object]:
    base = _recorded_base(repository)
    files = tuple(
        filter(None, _git(repository, "diff", "--name-only", f"{base}...HEAD").splitlines())
    )
    normalized = _impact_rules(_manifest(repository))
    # This frontend's internal boundary consumes the serialized evidence shape.
    selection = json.loads(json.dumps(asdict(select_paths(files, normalized))))
    return {
        "schema_version": 1,
        "status": "changed",
        "base": base,
        "source": _git(repository, "rev-parse", "HEAD"),
        "files": files,
        "selection": selection,
        "rules": selection["rules"],
        "profiles": selection["profiles"],
        "gates": selection["gates"],
        "shards": selection["shards"],
        "unexplained": selection["unexplained"],
        "requires_final": selection["requires_final"],
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
        if evidence_base is None or evidence_base == source or not _hosts_changes(repository):
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
    gate = "member" if kind == "member" else "final"
    manifest = _manifest(repository)
    selection = (
        _mapping(changed(repository, True)["selection"], "selection") if base is not None else None
    )
    selected_shards: tuple[str, ...] | None = None
    if isinstance(selection, dict):
        selected_shards, deferred = _member_shards(manifest, selection)
        if deferred:
            selection = dict(selection)
            selection["reasons"] = _strings(selection["reasons"], "selection.reasons") + [
                f"world shard {name} deferred to final" for name in deferred
            ]
    evidence_base = _git(repository, "rev-parse", base) if base else evidence_base
    evidence = _run_gate(repository, gate, selected_shards, base=evidence_base, selection=selection)
    payload = {
        "schema_version": 3,
        "kind": kind,
        "source": source,
        "base": _git(repository, "rev-parse", base) if base else evidence_base,
        "validated_at": datetime.now(UTC).isoformat(),
        "valid": True,
        "evidence": json.loads(evidence.to_json()),
    }

    if reconciliation is not None and approvals is not None:
        payload["delivery_review"] = {
            "approvals": approvals,
            "reconciliation": reconciliation,
        }
    receipt = _write_receipt(repository, kind, payload)
    return {**payload, "status": "ready" if kind == "member" else "final", "receipt": str(receipt)}


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


def _hosts_changes(repository: Path) -> bool:
    """Report whether this tree can hold a Change at all.

    Decided by the specification authority the manifest declares, so a
    repository which arranges its change packages differently is judged by its
    own declaration rather than by a directory name assumed here.
    """

    declared = _mapping(_manifest(repository).get("repository"), "repository")
    pattern = declared.get("specifications")
    if not isinstance(pattern, str) or not pattern:
        raise AdmissionError("repository.specifications must be a non-empty pattern")
    return any(repository.glob(pattern))


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


def _admission_evidence(member: Path, tip: str) -> str:
    """Locate evidence proving what this member's own selection requires.

    Evidence is matched by observed tree and by shard command digest, never by
    commit identity, receipt gate, or shard name: an amended trailer, an
    equivalent rebase, a renamed shard, and a completed final gate all prove
    the same work.
    """

    manifest = _manifest(member)
    selection = changed(member, True)["selection"]
    if not isinstance(selection, dict):
        raise AdmissionError("member selection is unavailable")
    required_names, _ = _member_shards(manifest, selection)
    validation = _mapping(manifest.get("validation"), "validation")
    raw_shards = validation["shards"]
    if not isinstance(raw_shards, list):
        raise AdmissionError("validation.shards must be an array")
    commands = {
        str(shard["name"]): tuple(_strings(shard["command"], "shard.command"))
        for item in raw_shards
        for shard in (_mapping(item, "validation shard"),)
    }
    required = {command_digest(commands[name]) for name in required_names}
    tree = _git(member, "rev-parse", f"{tip}^{{tree}}")
    for path in sorted(_receipt_root(member).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            evidence = payload["evidence"]
            proven = {str(outcome["command_digest"]) for outcome in evidence["execution"]["shards"]}
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        if evidence["identity"]["tree"] != tree or evidence.get("valid") is not True:
            continue
        if required <= proven:
            return path.name
    if selection["requires_final"]:
        rules = ",".join(_strings(selection["rules"], "selection.rules"))
        return "deferred:requires-final:" + (rules or "unexplained")
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
        (git, "patch-id", "--stable"), input=diff.stdout, check=False, capture_output=True
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


def _attested_base(repository: Path, tip: str) -> str | None:
    """Read the base a batch's provenance commit attests to.

    This is the durable attestation, not the authority: operations read the
    workspace record. Delivery compares the two.
    """

    history = _git(repository, "log", "--first-parent", "--format=%B%x00", tip)
    marker = re.search(r"^Signetum-Batch-Base:\s*(\S+)$", history, re.MULTILINE)
    return marker.group(1) if marker else None


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
        updated, count = re.subn(
            r"^Superseded by:.*$",
            f"Superseded by: {formal_path.name}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if count == 0:
            raise AdmissionError(f"decision declares no supersession field: {reference}")
        target.write_text(updated, encoding="utf-8")


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
            if candidate == batch / formal_path:
                # Numbering is what accepts a proposal, so the decision it
                # renames stops declaring itself one.
                rewritten = re.sub(
                    r"^Status:\s*Proposed\s*$", "Status: Accepted", rewritten, flags=re.MULTILINE
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
        if not plans and _hosts_changes(member):
            raise AdmissionError("member commit has no Delivers Plan trailer")
        record = {"branch": member_branch, "original": member_tip, "worktree": str(member)}
        if _is_ancestor(batch, member_tip, batch_tip):
            unchanged.append(record)
            continue
        batch_base = _recorded_base(batch)
        ready_evidence = _admission_evidence(member, member_tip)
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
    opened = _open_workspace(
        repository,
        branch,
        "HEAD",
        kind="batch",
        members=tuple(str(member.resolve()) for member in members),
    )
    batch = Path(str(opened["worktree"]))
    _git(
        batch,
        "commit",
        "--allow-empty",
        "-m",
        "signetum: open provenance batch",
        "-m",
        f"Signetum-Batch-Format: 1\nSignetum-Batch-Base: {approved_base}",
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
            for key, value in re.findall(r"^Signetum-([^:]+):\s*(.+)$", body, re.MULTILINE)
        }
        if fields.get("Original") != original:
            raise AdmissionError("admission provenance original does not match merge parent")
        summary = _git(repository, "show", "-s", "--format=%s", original)
        member_plans = re.findall(r"^Signetum-Plan:\s*(.+)$", body, re.MULTILINE)
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
    source_matches = tuple(
        workspace for workspace in worktrees.values() if workspace.path == source.resolve()
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
    except AdmissionError as error:
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
