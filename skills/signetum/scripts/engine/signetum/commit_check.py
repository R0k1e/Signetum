"""Refuse a workspace commit that implements before its committed approval.

Git runs the installed ``reference-transaction`` hook before a ref moves. For a
new single-parent commit on the tip of a registered workspace branch it applies
the approval-order verdict final applies to batch commits and ready applies to
member commits, through the same functions, to that one commit.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

from signetum.change.scope import ChangeError, batch_owned_commits, require_member_commit
from signetum.git import GitError, git_output, repository_path, run_git
from signetum.manifest import ManifestError, parse_manifest
from signetum.workspaces import WorkspaceError, read_record, state_root

HOOK_NAME = "reference-transaction"
MARK = "# signetum-commit-check"
_ZERO = re.compile(r"0+")


def hook_script(engine: str) -> str:
    """The hook body; it starts the engine only for prepared branch updates."""

    quoted = shlex.quote(engine)
    return f"""#!/bin/sh
{MARK}: written by Signetum workspace-open and batch-open, rewritten by each.
[ "$1" = prepared ] || exit 0
input=$(cat)
case "$input" in *" refs/heads/"*) ;; *) exit 0 ;; esac
engine={quoted}
if [ ! -x "$engine" ]; then
    printf '%s\\n' "signetum: commit check skipped: its engine $engine is missing; run \
workspace-open for this workspace again to reinstall it. ready and final still check approval \
order." >&2
    exit 0
fi
printf '%s\\n' "$input" | "$engine" -I -B -m signetum.commit_check
"""


def _inside_worktree(directory: Path) -> bool:
    existing = directory
    while not existing.is_dir():
        existing = existing.parent
    completed = run_git(existing, "rev-parse", "--is-inside-work-tree")
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def install_commit_check(worktree: Path) -> dict[str, object]:
    """Install or refresh the hook in the effective hooks directory, never replacing another."""

    hooks = repository_path(worktree, "rev-parse", "--git-path", "hooks")
    target = hooks / HOOK_NAME
    if _inside_worktree(hooks):
        return {
            "status": "skipped",
            "hook": str(target),
            "cause": "the hooks directory lies inside a worktree; writing there changes source",
        }
    if target.exists() and MARK not in target.read_text(encoding="utf-8", errors="replace"):
        return {
            "status": "skipped",
            "hook": str(target),
            "cause": f"a {HOOK_NAME} hook not written by Signetum exists; call "
            f"{sys.executable} -I -B -m signetum.commit_check from it with the same input "
            "to add the check",
        }
    hooks.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".signetum-hook-", dir=hooks)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(hook_script(sys.executable))
        Path(temporary).chmod(0o755)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"status": "installed", "hook": str(target)}


def judge(repository: Path, branch: str, old: str, new: str) -> ChangeError | None:
    """The refusal for ``new`` on ``branch``, or None when it passes or is not judged."""

    try:
        record = read_record(state_root(repository), branch)
    except WorkspaceError:
        return None
    if git_output(repository, "rev-list", "--parents", "-n", "1", new).split()[1:] != [old]:
        # Merges, branch moves and rewrites keep their own provenance checks.
        return None
    manifest = parse_manifest(git_output(repository, "show", f"{new}:signetum.toml"))
    try:
        if record.kind == "batch":
            batch_owned_commits(repository, manifest, record.base, new, judged=new)
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
