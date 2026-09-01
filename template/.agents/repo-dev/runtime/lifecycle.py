"""Self-contained lifecycle authority for explicit RepoSeal batch delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess  # nosec B404 -- fixed tuple commands, never a shell
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from shutil import which

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deviations import DeviationError, approval_view, reconciliation_summary


class AdmissionError(ValueError):
    """The requested member cannot be admitted safely."""


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
    common = Path(_git(repository, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repository / common
    root = common.resolve() / "reposeal" / "validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_receipt(repository: Path, kind: str, payload: dict[str, object]) -> Path:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    identity = hashlib.sha256(encoded.encode()).hexdigest()
    target = _receipt_root(repository) / f"{kind}-{identity}.json"
    target.write_text(encoded, encoding="utf-8")
    return target


def _manifest(repository: Path) -> dict[str, object]:
    manifest = repository / "reposeal.toml"
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        if data.get("schema_version") != 2:
            raise AdmissionError("unsupported reposeal.toml schema")
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


def _run_gate(
    repository: Path, kind: str, selected_shards: tuple[str, ...] | None = None
) -> tuple[str, ...]:
    data = _manifest(repository)
    validation = data.get("validation")
    if not isinstance(validation, dict):
        raise AdmissionError("validation graph is unavailable")
    raw_shards = validation.get("shards")
    raw_gates = validation.get("gates")
    if not isinstance(raw_shards, list) or not isinstance(raw_gates, list):
        raise AdmissionError("validation graph must contain shards and gates")
    commands: dict[str, tuple[str, ...]] = {}
    for shard in raw_shards:
        if not isinstance(shard, dict) or not isinstance(shard.get("name"), str):
            raise AdmissionError("validation shard is invalid")
        command = shard.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(argument, str) and argument for argument in command)
        ):
            raise AdmissionError("validation shard commands must be non-empty argv lists")
        commands[shard["name"]] = tuple(command)
    gate = next(
        (item for item in raw_gates if isinstance(item, dict) and item.get("name") == kind),
        None,
    )
    if gate is None or not isinstance(gate.get("shards"), list):
        raise AdmissionError(f"validation gate is unavailable: {kind}")
    names = tuple(gate["shards"]) if selected_shards is None else selected_shards
    for name in names:
        command = commands.get(name)
        if command is None:
            raise AdmissionError(f"validation shard is unavailable: {name}")
        _run_tool(repository, command, capture_output=False)
    return names


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
    return {
        "schema_version": 1,
        "status": "opened",
        "branch": branch,
        "base": base,
        "source": source,
        "worktree": str(workspace.path),
    }


def changed(repository: Path, base: str, explain: bool) -> dict[str, object]:
    files = tuple(
        filter(None, _git(repository, "diff", "--name-only", f"{base}...HEAD").splitlines())
    )
    try:
        manifest = _manifest(repository)
        impact = _mapping(manifest.get("impact"), "impact")
        rules = [_mapping(item, "impact rule") for item in _array(impact["rules"], "impact.rules")]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise AdmissionError(f"invalid impact authority: {error}") from error
    matched: list[dict[str, object]] = []
    unexplained: list[str] = []
    for path in files:
        selected = [
            rule
            for rule in rules
            if any(
                fnmatch(path, pattern)
                or (pattern.endswith("/**") and path == pattern.removesuffix("/**"))
                for pattern in _strings(rule.get("paths", []), "impact.paths")
            )
        ]
        if not selected:
            unexplained.append(path)
        for rule in selected:
            if rule not in matched:
                matched.append(rule)

    def union(field: str) -> list[str]:
        values: list[str] = []
        for rule in matched:
            raw_values = rule.get(field, [])
            if not isinstance(raw_values, list):
                raise AdmissionError(f"impact rule {field} must be an array")
            for value in raw_values:
                if not isinstance(value, str):
                    raise AdmissionError(f"impact rule {field} values must be strings")
                if value not in values:
                    values.append(value)
        return values

    selection = {
        "changed_paths_digest": "sha256:"
        + hashlib.sha256(json.dumps(files, separators=(",", ":")).encode()).hexdigest(),
        "rules": [rule["name"] for rule in matched],
        "profiles": union("profiles"),
        "gates": union("gates"),
        "shards": union("shards"),
        "modified_tests": [
            path
            for path in files
            if path.startswith("tests/") or "/tests/" in path or Path(path).name.startswith("test_")
        ],
        "external_obligations": [],
        "unexplained": unexplained,
        "requires_final": bool(unexplained)
        or any(rule.get("requires_final") is True for rule in matched),
        "reasons": [f"impact rule {rule['name']} matched" for rule in matched],
    }
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


def validate(repository: Path, base: str | None, kind: str) -> dict[str, object]:
    _require_clean(repository)
    source = _git(repository, "rev-parse", "HEAD")
    if base is not None and source == _git(repository, "rev-parse", base):
        raise AdmissionError("source has no commits beyond the approved base")
    evidence_base = _batch_base(repository, source) if kind == "final" else None
    if kind == "final":
        proposals = _proposal_paths(repository)
        if proposals:
            raise AdmissionError(f"final refuses proposal decisions: {', '.join(proposals)}")
        _require_numbering_base(repository, evidence_base, source)
        if evidence_base is None:
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
    selection = changed(repository, base, True)["selection"] if base is not None else None
    selected_shards: tuple[str, ...] | None = None
    if isinstance(selection, dict):
        validation = _mapping(manifest.get("validation"), "validation")
        required = _strings(validation.get("member_required", []), "member_required")
        for name in selection["shards"]:
            if name not in required:
                required.append(name)
        raw_gates = validation["gates"]
        if not isinstance(raw_gates, list):
            raise AdmissionError("validation.gates must be an array")
        gates = {
            str(gate["name"]): _strings(gate["shards"], "gate.shards")
            for item in raw_gates
            for gate in (_mapping(item, "validation gate"),)
        }
        for name in selection["gates"]:
            for shard in gates.get(name, ()):
                if shard not in required:
                    required.append(shard)
        if selection["unexplained"]:
            for shard in gates["member"]:
                if shard not in required:
                    required.append(shard)
        selected_shards = tuple(required)
    executed_shards = _run_gate(repository, gate, selected_shards)
    configuration = (repository / "reposeal.toml").read_bytes()
    profiles = _mapping(manifest.get("profiles", {}), "profiles")
    repository_config = _mapping(manifest.get("repository"), "repository")
    reposeal_config = _mapping(manifest.get("reposeal"), "reposeal")
    validation_config = _mapping(manifest.get("validation"), "validation")
    identity = {
        "commit": source,
        "tree": _git(repository, "rev-parse", "HEAD^{tree}"),
        "base": _git(repository, "rev-parse", base) if base else evidence_base,
        "configuration": {
            "path": "reposeal.toml",
            "digest": "sha256:" + hashlib.sha256(configuration).hexdigest(),
        },
        "profiles": sorted(_strings(profiles.get("enabled", []), "profiles.enabled")),
        "graph": "sha256:"
        + hashlib.sha256(
            json.dumps(validation_config, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "lockfiles": [
            {
                "path": path,
                "digest": "sha256:" + hashlib.sha256((repository / path).read_bytes()).hexdigest(),
            }
            for path in sorted(
                _strings(repository_config.get("lockfiles", []), "repository.lockfiles")
            )
        ],
        "tools": [],
    }
    payload = {
        "schema_version": 3,
        "kind": kind,
        "source": source,
        "base": _git(repository, "rev-parse", base) if base else evidence_base,
        "validated_at": datetime.now(UTC).isoformat(),
        "valid": True,
        "evidence": {
            "schema_version": 3,
            "protocol": reposeal_config["evidence_protocol"],
            "schema_digest": reposeal_config["evidence_schema_digest"],
            "identity": identity,
            "selection": selection,
            "execution": {
                "gates": [gate],
                "shards": sorted(executed_shards),
                "external_obligations": [],
            },
            "completeness": {
                "member": gate == "member",
                "final": gate == "final",
                "required_shards": sorted(executed_shards),
            },
            "provenance": {"stable_patch_id": None},
            "extensions": {},
            "valid": True,
        },
    }
    if reconciliation is not None and approvals is not None:
        payload["delivery_review"] = {
            "approvals": approvals,
            "reconciliation": reconciliation,
        }
    receipt = _write_receipt(repository, kind, payload)
    return {**payload, "status": "ready" if kind == "member" else "final", "receipt": str(receipt)}


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


def _ready_evidence(repository: Path, source: str, base: str) -> str:
    matches: list[str] = []
    for path in sorted(_receipt_root(repository).glob("member-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            payload.get("kind") == "member"
            and payload.get("source") == source
            and payload.get("base") == base
            and payload.get("valid") is True
        ):
            matches.append(path.name)
    if not matches:
        raise AdmissionError("member has no ready evidence for its exact commit and base")
    return matches[-1]


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
    return tuple(
        line for line in _git(repository, "ls-files", "*ADP-proposal-*.md").splitlines() if line
    )


def _batch_base(repository: Path, tip: str) -> str | None:
    history = _git(repository, "log", "--first-parent", "--format=%B%x00", tip)
    marker = re.search(r"^RepoSeal-Batch-Base:\s*(\S+)$", history, re.MULTILINE)
    if marker:
        return marker.group(1)
    merges = _git(repository, "rev-list", "--first-parent", "--merges", tip).splitlines()
    for commit in merges:
        message = _git(repository, "show", "-s", "--format=%B", commit)
        match = re.search(r"^RepoSeal-Base:\s*(\S+)$", message, re.MULTILINE)
        if match:
            return match.group(1)
    return None


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
        batch_base = _batch_base(batch, batch_tip) or batch_tip
        ready_evidence = _ready_evidence(member, member_tip, batch_base)
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

    decisions = _number_proposals(batch, _batch_base(batch, _git(batch, "rev-parse", "HEAD")) or "")
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
    batch_base = _batch_base(batch, committed)
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
    if _batch_base(source, expected_tip) != expected_base:
        raise AdmissionError("batch numbering and provenance differ from expected base")
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
    diagnostic.add_argument("base")
    diagnostic.add_argument("--explain", action="store_true")
    readiness = commands.add_parser("ready")
    readiness.add_argument("base")
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
            result = changed(repository, parsed.base, parsed.explain)
        elif parsed.command == "ready":
            result = validate(repository, parsed.base, "member")
        elif parsed.command == "batch-open":
            result = batch_open(repository, tuple(parsed.member))
        elif parsed.command == "batch-admit":
            result = admit(parsed.batch.resolve(), tuple(parsed.member))
        elif parsed.command == "batch-continue":
            result = continue_batch(parsed.batch.resolve())
        elif parsed.command == "final":
            result = validate(repository, None, "final")
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
