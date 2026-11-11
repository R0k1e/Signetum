"""Guard Git's negotiated remote old identity while retaining existing hooks."""

from __future__ import annotations

import shlex
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from signetum.git import repository_path

if TYPE_CHECKING:
    from signetum.delivery import GitCommand


def guarded_push(
    repository: Path,
    *,
    git: GitCommand,
    target_branch: str,
    expected_base: str,
    delivery_commit: str,
) -> str:
    """Git receives the same negotiated old OID after the pre-push guard passes."""
    original = repository_path(repository, "rev-parse", "--git-path", "hooks/pre-push")
    with tempfile.TemporaryDirectory(prefix="signetum-publication-hooks-") as directory:
        hooks = Path(directory)
        if original.parent.is_dir():
            for path in original.parent.iterdir():
                if path.name != "pre-push":
                    (hooks / path.name).symlink_to(
                        path.resolve(), target_is_directory=path.is_dir()
                    )
        command = (
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).with_name("publication_guard.py")),
            "refs/heads/" + target_branch,
            expected_base,
            delivery_commit,
            str(original),
        )
        hook = hooks / "pre-push"
        hook.write_text("#!/bin/sh\nexec " + shlex.join(command) + ' "$@"\n', encoding="utf-8")
        hook.chmod(0o755)
        return git(
            repository,
            "-c",
            f"core.hooksPath={hooks}",
            "push",
            "origin",
            f"{delivery_commit}:refs/heads/{target_branch}",
        )
