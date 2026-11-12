"""Install and verify the early immutable implementation and record verdicts."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from signetum.change.scope import (
    ChangeError,
    DeliveryScope,
    changed_commitments,
    commit_attribution,
    delivery_scope,
    require_member_commit,
)
from signetum.decision_proposals import proposal_paths
from signetum.git import GitError, git_output, isolated_git_environment, repository_path, run_git
from signetum.manifest import ManifestError, parse_manifest
from signetum.operation_records import (
    commit_message,
    legacy_pending_trailers,
    pending_message,
    pending_tree,
)
from signetum.operations import AdmissionError
from signetum.runtime_identity import engine_source
from signetum.synchronization import prepared_merge, preserves_merge_message
from signetum.workspaces import WorkspaceError, read_record, state_root

HOOK_NAME = "reference-transaction"
MARK = "# signetum-commit-check"
_ZERO = re.compile(r"0+")
CHAIN = """input=$(cat)
shim="$(git rev-parse --git-common-dir)/signetum/hooks/reference-transaction"
if [ -x "$shim" ]; then printf '%s\\n' "$input" | "$shim" "$@" || exit $?; fi"""


def hook_script(engine: str, *, launcher: bool = False) -> str:
    """A stable entry touches the probe before filtering branch transactions."""
    command = (
        shlex.quote(engine) + " maintenance commit-check"
        if launcher
        else shlex.quote(engine) + " -I -B -m signetum.maintenance commit-check"
    )
    return f"""#!/bin/sh
{MARK}
[ "$1" = prepared ] || exit 0
if [ -n "${{SIGNETUM_COMMIT_CHECK_PROBE:-}}" ]; then
    : > "$SIGNETUM_COMMIT_CHECK_PROBE" || exit 1
fi
input=$(cat)
case "$input" in *" refs/heads/"*) ;; *) exit 0 ;; esac
printf '%s\\n' "$input" | {command}
"""


def _inside_worktree(directory: Path) -> bool:
    existing = directory
    while not existing.is_dir():
        existing = existing.parent
    completed = run_git(existing, "rev-parse", "--is-inside-work-tree")
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def _write_hook(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".signetum-hook-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        Path(temporary).chmod(0o755)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _probe(worktree: Path, target: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="signetum-hook-probe-") as temporary:
        probe = Path(temporary) / "observed"
        ref = "refs/signetum/probe/" + uuid4().hex
        environment = isolated_git_environment()
        environment["SIGNETUM_COMMIT_CHECK_PROBE"] = str(probe)
        created = run_git(worktree, "update-ref", ref, "HEAD", environment=environment)
        try:
            active = created.returncode == 0 and probe.exists()
        finally:
            deleted = run_git(worktree, "update-ref", "-d", ref, environment=environment)
        return {
            "status": "active" if active and deleted.returncode == 0 else "inactive",
            "hook": str(target),
            **(
                {}
                if active and deleted.returncode == 0
                else {
                    "cause": created.stderr.strip()
                    or deleted.stderr.strip()
                    or "the effective hook did not invoke the Signetum shim",
                    "chaining": CHAIN,
                }
            ),
        }


def _cache(worktree: Path) -> Path:
    return repository_path(worktree, "rev-parse", "--git-path", "signetum-commit-check.json")


def _signature(target: Path) -> list[object]:
    stat = target.stat() if target.exists() else None
    return [str(target), stat.st_mtime_ns if stat else None, stat.st_mode if stat else None]


def commit_check_status(worktree: Path, *, refresh: bool = False) -> dict[str, object]:
    target = repository_path(worktree, "rev-parse", "--git-path", "hooks") / HOOK_NAME
    signature = _signature(target)
    cache = _cache(worktree)
    if not refresh:
        try:
            document = json.loads(cache.read_text())
            if document["signature"] == signature:
                return document["result"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    result = _probe(worktree, target)
    cache.write_text(json.dumps({"signature": signature, "result": result}) + "\n")
    return result


def install_commit_check(worktree: Path) -> dict[str, object]:
    """Refresh the local shim, preserve project hooks and probe the actual chain."""
    shim = state_root(worktree) / "hooks" / HOOK_NAME
    launcher = engine_source(worktree) == "skill"
    engine = (
        str(Path(os.environ["SIGNETUM_SKILL"]) / "scripts/signetum") if launcher else sys.executable
    )
    _write_hook(shim, hook_script(engine, launcher=launcher))
    target = repository_path(worktree, "rev-parse", "--git-path", "hooks") / HOOK_NAME
    managed = target.exists() and MARK in target.read_text(encoding="utf-8", errors="replace")
    if not _inside_worktree(target.parent) and (not target.exists() or managed):
        _write_hook(target, "#!/bin/sh\n" + MARK + "\n" + CHAIN + "\n")
    return commit_check_status(worktree, refresh=True)


def judge(repository: Path, branch: str, old: str, new: str) -> ChangeError | None:
    """The refusal for ``new`` on ``branch``, or None when it passes or is not judged."""

    try:
        record = read_record(state_root(repository), branch)
    except WorkspaceError:
        return None
    parents = git_output(repository, "rev-list", "--parents", "-n", "1", new).split()[1:]
    if len(parents) == 2 and parents[0] == old:
        merge_head = run_git(repository, "rev-parse", "--verify", "MERGE_HEAD")
        if merge_head.returncode == 0 and merge_head.stdout.strip() == parents[1]:
            follow = "; then run batch-continue" if record.kind == "batch" else ""
            try:
                frozen = pending_message(repository, branch, old, parents[1])
            except AdmissionError as error:
                return ChangeError(str(error), expected="retry the recorded operation" + follow)
            if frozen is not None:
                if commit_message(repository, new) != frozen:
                    return ChangeError(
                        "merge message does not match the recorded operation",
                        expected=(
                            "commit with git commit --no-edit to keep the recorded message" + follow
                        ),
                    )
                expected_tree = pending_tree(repository, branch, old, parents[1])
                if (
                    expected_tree is not None
                    and git_output(repository, "rev-parse", f"{new}^{{tree}}") != expected_tree
                ):
                    return ChangeError(
                        "merge tree does not match the recorded operation",
                        expected=(
                            "commit with git commit --no-edit to keep the recorded message" + follow
                        ),
                    )
            else:
                trailers = legacy_pending_trailers(repository, old, parents[1])
                if trailers is not None:
                    prepared = trailers
                    if not preserves_merge_message(repository, new, prepared):
                        return ChangeError(
                            "merge message does not preserve the prepared Signetum trailers",
                            expected=(
                                "commit with git commit --no-edit to preserve the prepared "
                                "merge message" + follow
                            ),
                        )
                else:
                    prepared_file = prepared_merge(repository, old, parents[1])
                    if prepared_file is not None and not preserves_merge_message(
                        repository, new, prepared_file
                    ):
                        return ChangeError(
                            "merge message does not preserve the prepared Signetum trailers",
                            expected=(
                                "commit with git commit --no-edit to preserve the prepared "
                                "merge message" + follow
                            ),
                        )
    if parents != [old]:
        # Unrelated merges, branch moves and rewrites keep their provenance checks.
        return None
    manifest = parse_manifest(git_output(repository, "show", f"{new}:signetum.toml"))
    try:
        proposals = proposal_paths(repository, manifest, old, new)
        if proposals:
            raise ChangeError("commit adds or modifies proposal decisions: " + ", ".join(proposals))
        # The parent contains this workspace's newly approved packages too. Only
        # packages already held at the registered base are delivered authority.
        delivered = delivery_scope(repository, manifest, record.base, new)
        changed = delivery_scope(repository, manifest, old, new)
        delivered_ids = {item.change_id for item in delivered.previously_delivered}
        scope = DeliveryScope(
            (),
            tuple(item for item in changed.previously_delivered if item.change_id in delivered_ids),
        )
        rewritten = changed_commitments(repository, manifest, old, new, scope)
        if rewritten:
            raise ChangeError("commit rewrites delivered commitments: " + ", ".join(rewritten))
        if record.kind == "batch":
            commit_attribution(repository, manifest, record, new)
        else:
            require_member_commit(repository, manifest, record.base, new)
    except ChangeError as error:
        return error
    return None


def main() -> int:
    try:
        repository = Path(git_output(Path.cwd(), "rev-parse", "--show-toplevel"))
    except GitError:
        return 0
    for line in sys.stdin.read().splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        old, new, ref = fields
        if not ref.startswith("refs/heads/") or _ZERO.fullmatch(old) or _ZERO.fullmatch(new):
            continue
        branch = ref.removeprefix("refs/heads/")
        try:
            refusal = judge(repository, branch, old, new)
        except (GitError, ManifestError, WorkspaceError, ValueError, OSError) as error:
            print(
                f"signetum: commit check skipped for {branch}: {error}; "
                "ready and final still check approval order.",
                file=sys.stderr,
            )
            continue
        if refusal is not None:
            print(f"signetum: commit refused on {branch}: {refusal}", file=sys.stderr)
            if refusal.expected:
                print(refusal.expected, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
