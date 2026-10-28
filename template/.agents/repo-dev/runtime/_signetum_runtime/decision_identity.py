# Generated from signetum.decision_identity; edit the engine source and regenerate.
"""Replay explicit, committed final-numbering identity moves."""

import json
import re
from pathlib import Path, PurePosixPath

from .git import git_output
from .operations import AdmissionError


def numbered_targets(repository: Path, base: str, tip: str, directory: str) -> dict[str, str]:
    moves: dict[str, str] = {}
    for commit in git_output(
        repository, "rev-list", "--reverse", "--first-parent", "--no-merges", f"{base}..{tip}"
    ).splitlines():
        body = git_output(repository, "show", "-s", "--format=%B", commit)
        entries = re.findall(r"^Signetum-Decision-Rename: (.+)$", body, re.MULTILINE)
        if not entries:
            continue
        if re.findall(r"^Signetum-Decision-Base: (.+)$", body, re.MULTILINE) != [base]:
            raise AdmissionError("decision identity moves do not bind the batch base")
        for entry in entries:
            try:
                pair = json.loads(entry)
                if (
                    not isinstance(pair, list)
                    or len(pair) != 2
                    or not all(isinstance(value, str) for value in pair)
                ):
                    raise ValueError("expected two decision paths")
                old, new = map(PurePosixPath, pair)
                numbered = re.fullmatch(r"ADP-\d{4}-(.+)\.md", new.name)
                if (
                    old.parent != PurePosixPath(directory)
                    or new.parent != old.parent
                    or ".." in old.parts
                    or old.is_absolute()
                    or numbered is None
                    or old.name != f"ADP-{numbered[1]}.md"
                    or str(old) in moves
                ):
                    raise ValueError("invalid or repeated numbering identity")
                if (
                    git_output(repository, "ls-tree", "--name-only", commit, "--", str(old))
                    or not git_output(
                        repository, "ls-tree", "--name-only", f"{commit}^", "--", str(old)
                    )
                    or not git_output(repository, "ls-tree", "--name-only", commit, "--", str(new))
                ):
                    raise ValueError("numbering identity is not a committed move")
                moves[str(old)] = str(new)
            except (ValueError, TypeError) as error:
                raise AdmissionError(f"invalid decision identity move: {error}") from error
    return moves
