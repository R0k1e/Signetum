"""Self-contained lifecycle authority for explicit RepoSeal batch delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess  # nosec B404 -- fixed tuple commands, never a shell
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import which


class AdmissionError(ValueError):
    """The requested member cannot be admitted safely."""


def _receipt_root(repository: Path) -> Path:
    common = Path(_git(repository, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repository / common
    root = common.resolve() / "reposeal-receipts"
    root.mkdir(exist_ok=True)
    return root


def _write_receipt(repository: Path, kind: str, payload: dict[str, object]) -> Path:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    identity = hashlib.sha256(encoded.encode()).hexdigest()
    target = _receipt_root(repository) / f"{kind}-{identity}.json"
    target.write_text(encoded, encoding="utf-8")
    return target


def _run_gate(repository: Path, kind: str) -> None:
    manifest = repository / "reposeal.yaml"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        commands = data["validation"][kind]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise AdmissionError(f"invalid validation authority: {error}") from error
    if not isinstance(commands, list) or not commands:
        raise AdmissionError(f"validation.{kind} must contain at least one command")
    for command in commands:
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(argument, str) and argument for argument in command)
        ):
            raise AdmissionError(f"validation.{kind} commands must be non-empty argv lists")
        completed = subprocess.run(tuple(command), cwd=repository, check=False)  # nosec B603
        if completed.returncode:
            raise AdmissionError("repository validation failed")


def workspace_open(repository: Path, branch: str, base: str) -> dict[str, object]:
    root = Path(_git(repository, "rev-parse", "--show-toplevel"))
    destination = root.parent / f"{root.name}-{branch.replace('/', '-')}"
    if destination.exists():
        raise AdmissionError(f"workspace path already exists: {destination}")
    _git(root, "worktree", "add", "-b", branch, str(destination), base)
    return {
        "schema_version": 1,
        "status": "opened",
        "branch": branch,
        "base": base,
        "worktree": str(destination),
    }


def changed(repository: Path, base: str, explain: bool) -> dict[str, object]:
    files = tuple(
        filter(None, _git(repository, "diff", "--name-only", f"{base}...HEAD").splitlines())
    )
    return {
        "schema_version": 1,
        "status": "changed",
        "base": base,
        "source": _git(repository, "rev-parse", "HEAD"),
        "files": files,
        "requires_final": bool(files),
        "explain": explain,
    }


def validate(repository: Path, base: str | None, kind: str) -> dict[str, object]:
    _require_clean(repository)
    source = _git(repository, "rev-parse", "HEAD")
    if base is not None and source == _git(repository, "rev-parse", base):
        raise AdmissionError("source has no commits beyond the approved base")
    _run_gate(repository, "member" if kind == "member" else "final")
    payload = {
        "schema_version": 1,
        "kind": kind,
        "source": source,
        "base": _git(repository, "rev-parse", base) if base else None,
        "validated_at": datetime.now(UTC).isoformat(),
        "valid": True,
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


def admit(batch: Path, members: tuple[Path, ...]) -> dict[str, object]:
    _require_clean(batch)
    batch_branch = _branch(batch)
    if batch_branch in {"main", "master", "product"}:
        raise AdmissionError(f"refusing batch admission on delivery branch: {batch_branch}")

    admitted: list[dict[str, str]] = []
    unchanged: list[dict[str, str]] = []
    for raw_member in members:
        member = raw_member.resolve()
        if member == batch:
            raise AdmissionError("batch cannot admit itself")
        _require_clean(member)
        member_branch = _branch(member)
        member_tip = _git(member, "rev-parse", "HEAD")
        batch_tip = _git(batch, "rev-parse", "HEAD")
        record = {"branch": member_branch, "commit": member_tip, "worktree": str(member)}
        if _is_ancestor(batch, member_tip, batch_tip):
            unchanged.append(record)
            continue
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
                f"merge: admit {member_branch}",
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
        admitted.append(record)

    return {
        "schema_version": 1,
        "status": "admitted",
        "batch": str(batch),
        "batch_branch": batch_branch,
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
        "admitted": admitted,
        "unchanged": unchanged,
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
    return {
        "schema_version": 1,
        "status": "continued",
        "batch": str(batch),
        "batch_commit": _git(batch, "rev-parse", "HEAD"),
    }


def batch_open(repository: Path, members: tuple[Path, ...]) -> dict[str, object]:
    _require_clean(repository)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    branch = f"batch/{stamp}"
    root = Path(_git(repository, "rev-parse", "--show-toplevel"))
    batch = root.parent / f"{root.name}-batch-{stamp}"
    _git(root, "worktree", "add", "-b", branch, str(batch), "HEAD")
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
    final_receipts = sorted(_receipt_root(source).glob("final-*.json"))
    if not final_receipts:
        raise AdmissionError("no final receipt exists")
    matching_receipt = next(
        (
            path
            for path in final_receipts
            if (payload := json.loads(path.read_text(encoding="utf-8"))).get("source")
            == expected_tip
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
        summary = _git(repository, "show", "-s", "--format=%s", original)
        body = _git(repository, "show", "-s", "--format=%B", original)
        for declared in re.findall(r"^Delivers:\s*(.+)$", body, re.MULTILINE):
            plans.update(item.strip() for item in declared.split(",") if item.strip())
        members.append(
            {
                "branch": subject.removeprefix(prefix),
                "original": original,
                "integrated": merge_commit,
                "summary": summary,
            }
        )
    if not members:
        raise AdmissionError("batch contains no admitted member provenance")
    return members, sorted(plans)


def _worktree_branches(repository: Path) -> dict[str, Path]:
    output = _git(repository, "worktree", "list", "--porcelain")
    result: dict[str, Path] = {}
    current_path: Path | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree ")).resolve()
        elif line.startswith("branch refs/heads/") and current_path is not None:
            result[line.removeprefix("branch refs/heads/")] = current_path
    return result


def _cleanup_delivered_worktrees(
    target: Path, source: Path, members: list[dict[str, str]]
) -> tuple[list[str], list[dict[str, str]]]:
    worktrees = _worktree_branches(target)
    removed: list[str] = []
    retained: list[dict[str, str]] = []
    latest_members = {member["branch"]: member for member in members}
    for branch, member in latest_members.items():
        path = worktrees.get(branch)
        if path is None:
            continue
        try:
            _require_clean(path)
            if _git(path, "rev-parse", "HEAD") != member["original"]:
                retained.append({"branch": branch, "worktree": str(path), "reason": "advanced"})
                continue
            _git(target, "worktree", "remove", str(path))
            _git(target, "branch", "-d", branch)
            removed.append(str(path))
        except AdmissionError as error:
            retained.append({"branch": branch, "worktree": str(path), "reason": str(error)})

    source_branch = _branch(source)
    _git(target, "worktree", "remove", str(source))
    _git(target, "branch", "-d", source_branch)
    removed.append(str(source))
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
