"""Install and functionally verify the early immutable commit verdict."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which
from uuid import uuid4

from signetum.change.scope import ChangeError, commit_attribution, require_member_commit
from signetum.git import GitError, git_output, isolated_git_environment, repository_path, run_git
from signetum.manifest import ManifestError, parse_manifest
from signetum.runtime_identity import engine_source
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
        executable = which("git")
        if executable is None:
            raise GitError("Git executable is unavailable")
        environment = isolated_git_environment()
        environment["SIGNETUM_COMMIT_CHECK_PROBE"] = str(probe)

        def update(*arguments: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(  # noqa: S603 -- resolved Git and owned probe ref
                [executable, "-C", str(worktree), "update-ref", *arguments],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

        created = update(ref, "HEAD")
        try:
            active = created.returncode == 0 and probe.exists()
        finally:
            deleted = update("-d", ref)
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
    if git_output(repository, "rev-list", "--parents", "-n", "1", new).split()[1:] != [old]:
        # Merges, branch moves and rewrites keep their own provenance checks.
        return None
    manifest = parse_manifest(git_output(repository, "show", f"{new}:signetum.toml"))
    try:
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
