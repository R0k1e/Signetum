"""Replay explicit, committed final-numbering identity moves."""

import json
import re
from pathlib import Path, PurePosixPath

from signetum.git import git_output
from signetum.operation_records import legacy_commit, load_index, require_bound_commit
from signetum.operations import AdmissionError


def _record_move(moves: dict[str, str], old: str, new: str, directory: str) -> None:
    numbered = re.fullmatch(r"ADP-\d{4}-(.+)\.md", PurePosixPath(new).name)
    old_path, new_path = PurePosixPath(old), PurePosixPath(new)
    if (
        old_path.parent != PurePosixPath(directory)
        or new_path.parent != old_path.parent
        or ".." in old_path.parts
        or old_path.is_absolute()
        or numbered is None
        or old_path.name != f"ADP-proposal-{numbered[1]}.md"
        or str(old_path) in moves
    ):
        raise ValueError("invalid or repeated numbering identity")
    moves[str(old_path)] = str(new_path)


def numbered_targets(repository: Path, base: str, tip: str, directory: str) -> dict[str, str]:
    moves: dict[str, str] = {}
    index = load_index(repository)
    for commit in git_output(
        repository, "rev-list", "--reverse", "--first-parent", "--no-merges", f"{base}..{tip}"
    ).splitlines():
        document = index.for_commit(commit)
        if document is not None and document.get("kind") == "decision-mapping":
            require_bound_commit(repository, document)
            if document.get("attested_base") != base:
                raise AdmissionError("decision identity moves do not bind the batch base")
            pairs = document.get("mappings")
            if not isinstance(pairs, list):
                raise AdmissionError(
                    "invalid decision identity move: operation mappings are invalid"
                )
            try:
                for pair in pairs:
                    if (
                        not isinstance(pair, list)
                        or len(pair) != 2
                        or not all(isinstance(value, str) for value in pair)
                    ):
                        raise ValueError("expected two decision paths")
                    old, new = pair
                    _record_move(moves, old, new, directory)
                    if (
                        git_output(repository, "ls-tree", "--name-only", commit, "--", old)
                        or not git_output(
                            repository, "ls-tree", "--name-only", f"{commit}^", "--", old
                        )
                        or not git_output(repository, "ls-tree", "--name-only", commit, "--", new)
                    ):
                        raise ValueError("numbering identity is not a committed move")
            except (ValueError, TypeError) as error:
                raise AdmissionError(f"invalid decision identity move: {error}") from error
            continue
        body = git_output(repository, "show", "-s", "--format=%B", commit)
        entries = re.findall(r"^Signetum-Decision-Rename: (.+)$", body, re.MULTILINE)
        bases = re.findall(r"^Signetum-Decision-Base: (.+)$", body, re.MULTILINE)
        if not entries and not bases:
            continue
        if not legacy_commit(repository, commit):
            raise AdmissionError(
                "decision identity moves require a structured operation or legacy history"
            )
        if not entries:
            continue
        if bases != [base]:
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
                old, new = pair
                _record_move(moves, old, new, directory)
                if (
                    git_output(repository, "ls-tree", "--name-only", commit, "--", str(old))
                    or not git_output(
                        repository, "ls-tree", "--name-only", f"{commit}^", "--", str(old)
                    )
                    or not git_output(repository, "ls-tree", "--name-only", commit, "--", str(new))
                ):
                    raise ValueError("numbering identity is not a committed move")
            except (ValueError, TypeError) as error:
                raise AdmissionError(f"invalid decision identity move: {error}") from error
    return moves
