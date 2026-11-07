"""Refuse agent shell commands that lose work or bypass Signetum operations.

Reads one Claude Code or Codex PreToolUse payload on stdin. In a Git work tree
whose root holds signetum.toml, exit 2 blocks the command and prints one JSON line
naming the category and the operation to use; every other outcome, including a
command elsewhere or a guard failure, allows it. Standard library
only, compatible with Python 3.9.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import NamedTuple

USE = {
    "stash": "Keep work visible: commit your own paths explicitly instead of stashing.",
    "destructive-reset": "Inspect the worktree first (git status, git diff); "
    "commit or keep work instead of resetting it away.",
    "destructive-restore": "Inspect the worktree first (git status, git diff); "
    "change exact paths instead of discarding the tree.",
    "unbounded-delete": "Delete the exact owned subtree by its path.",
    "force-push": "Push without force, or deliver through signetum batch-deliver.",
    "pre-commit-dirty-tree": "Stage only the files to commit, or commit them, before "
    "running pre-commit; it checks out unstaged changes underneath you.",
    "direct-merge": "Synchronize through signetum maintenance workspace-sync, "
    "or integrate through signetum batch-admit.",
    "direct-rebase": "Integrate through signetum batch-admit and resolve "
    "conflicts with signetum batch-continue.",
    "direct-workspace-removal": "Remove workspaces through signetum maintenance cleanup "
    "or, with the owner's confirmation, signetum maintenance workspace-abandon.",
    "direct-workspace-creation": "Open workspaces through signetum workspace-open; "
    "for experiments use a git clone --shared under scratch.",
}

_OPERATORS = ("&&", "||", ";;", "|&", ";", "&", "|", "(", ")", "\n")
_RESERVED = {"!", "{", "}", "then", "else", "elif", "fi", "do", "done", "if", "while", "until"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_HEREDOC = re.compile(r"<<(-?)[ \t]*")


class Simple(NamedTuple):
    words: list[str]
    heredocs: list[str]


class Verdict(NamedTuple):
    category: str
    command: str


def _matching(text: str, start: int, opening: str, closing: str) -> int:
    """Index just past the closing delimiter that balances text[start - 1]."""

    depth, index = 1, start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "'":
            end = text.find("'", index + 1)
            index = len(text) if end < 0 else end + 1
            continue
        if char == '"':
            index = _double_quoted(text, index + 1, [], [])
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


def _double_quoted(text: str, index: int, out: list[str], nested: list[str]) -> int:
    while index < len(text):
        char = text[index]
        if char == '"':
            return index + 1
        if char == "\\" and index + 1 < len(text):
            out.append(text[index + 1])
            index += 2
            continue
        if text.startswith("$(", index) and not text.startswith("$((", index):
            end = _matching(text, index + 2, "(", ")")
            nested.append(text[index + 2 : end - 1])
            out.append(text[index:end])
            index = end
            continue
        if char == "`":
            end = text.find("`", index + 1)
            end = len(text) if end < 0 else end
            nested.append(text[index + 1 : end])
            out.append(text[index : end + 1])
            index = end + 1
            continue
        out.append(char)
        index += 1
    return index


def _parse(text: str) -> tuple[list[Simple], list[str]]:
    """Split shell text into simple commands and the scripts nested inside them."""

    commands: list[Simple] = []
    nested: list[str] = []
    words: list[str] = []
    heredocs: list[str] = []
    pending: list[tuple[str, bool]] = []
    word: list[str] = []
    in_word = False
    index = 0

    def finish_word() -> None:
        nonlocal in_word
        if in_word:
            words.append("".join(word))
            word.clear()
            in_word = False

    def finish_command() -> None:
        finish_word()
        if words or heredocs:
            commands.append(Simple(list(words), list(heredocs)))
        words.clear()
        heredocs.clear()

    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 < len(text) and text[index + 1] == "\n":
                index += 2
                continue
            word.append(text[index + 1 : index + 2])
            in_word = True
            index += 2
            continue
        if char == "'":
            end = text.find("'", index + 1)
            end = len(text) if end < 0 else end
            word.append(text[index + 1 : end])
            in_word = True
            index = end + 1
            continue
        if char == '"':
            index = _double_quoted(text, index + 1, word, nested)
            in_word = True
            continue
        if text.startswith("$(", index) and not text.startswith("$((", index):
            end = _matching(text, index + 2, "(", ")")
            nested.append(text[index + 2 : end - 1])
            word.append(text[index:end])
            in_word = True
            index = end
            continue
        if char == "`":
            end = text.find("`", index + 1)
            end = len(text) if end < 0 else end
            nested.append(text[index + 1 : end])
            word.append(text[index : end + 1])
            in_word = True
            index = end + 1
            continue
        if char in "<>" and index + 1 < len(text) and text[index + 1] == "(":
            end = _matching(text, index + 2, "(", ")")
            nested.append(text[index + 2 : end - 1])
            word.append(text[index:end])
            in_word = True
            index = end
            continue
        heredoc = _HEREDOC.match(text, index) if not text.startswith("<<<", index) else None
        if heredoc is not None:
            finish_word()
            index = heredoc.end()
            delimiter: list[str] = []
            while index < len(text) and text[index] not in " \t\n;&|<>()":
                if text[index] in "'\"":
                    quote = text[index]
                    end = text.find(quote, index + 1)
                    end = len(text) if end < 0 else end
                    delimiter.append(text[index + 1 : end])
                    index = end + 1
                    continue
                if text[index] == "\\":
                    index += 1
                    continue
                delimiter.append(text[index])
                index += 1
            pending.append(("".join(delimiter), heredoc.group(1) == "-"))
            continue
        if char == "#" and not in_word:
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        if char == "\n" and pending:
            finish_command()
            index += 1
            for delimiter_text, strip in pending:
                body: list[str] = []
                while index < len(text):
                    end = text.find("\n", index)
                    end = len(text) if end < 0 else end
                    line = text[index:end]
                    index = end + 1
                    if (line.lstrip("\t") if strip else line) == delimiter_text:
                        break
                    body.append(line)
                if commands:
                    commands[-1].heredocs.append("\n".join(body))
            pending.clear()
            continue
        if char == "&" and word and word[-1] in "<>":
            word.append(char)
            index += 1
            continue
        operator = next((op for op in _OPERATORS if text.startswith(op, index)), None)
        if operator is not None:
            finish_command()
            index += len(operator)
            continue
        if char in " \t\r":
            finish_word()
            index += 1
            continue
        word.append(char)
        in_word = True
        index += 1
    finish_command()
    return commands, nested


def _basename(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _unwrap(words: list[str]) -> list[str]:
    """Drop assignments, reserved words and command wrappers before the real command."""

    index = 0
    while index < len(words):
        word = words[index]
        name = _basename(word)
        if word in _RESERVED or _ASSIGNMENT.match(word):
            index += 1
        elif name in {"command", "builtin", "exec", "nohup", "time", "noglob"}:
            index += 1
            while index < len(words) and words[index].startswith("-"):
                index += 1
        elif name == "env":
            index += 1
            while index < len(words) and (
                words[index].startswith("-") or _ASSIGNMENT.match(words[index])
            ):
                if words[index] in {"-u", "-C", "-S", "--unset", "--chdir"}:
                    index += 1
                index += 1
        elif name in {"sudo", "doas"}:
            index += 1
            while index < len(words) and words[index].startswith("-"):
                if words[index] in {"-u", "-g", "-C", "-h", "-p", "-U"}:
                    index += 1
                index += 1
        elif name == "nice":
            index += 1
            while index < len(words) and words[index].startswith("-"):
                if words[index] == "-n":
                    index += 1
                index += 1
        elif name in {"timeout", "gtimeout"}:
            index += 1
            while index < len(words) and words[index].startswith("-"):
                if words[index] in {"-s", "-k", "--signal", "--kill-after"}:
                    index += 1
                index += 1
            index += 1
        elif name == "mise" and index + 1 < len(words) and words[index + 1] in {"exec", "x"}:
            rest = words[index + 2 :]
            if "--" not in rest:
                return []
            index = index + 2 + rest.index("--") + 1
        else:
            return words[index:]
    return []


def _flags(arguments: list[str]) -> tuple[set[str], set[str], list[str]]:
    """Long options, short option letters and positional words, stopping at --."""

    long: set[str] = set()
    short: set[str] = set()
    positional: list[str] = []
    for position, argument in enumerate(arguments):
        if argument == "--":
            positional.extend(arguments[position + 1 :])
            break
        if argument.startswith("--"):
            long.add(argument.split("=", 1)[0])
        elif argument.startswith("-") and len(argument) > 1:
            short.update(argument[1:])
        else:
            positional.append(argument)
    return long, short, positional


_GIT_VALUE_OPTIONS = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--config-env",
    "--super-prefix",
}


def _git(arguments: list[str]) -> tuple[str | None, list[str]]:
    """Subcommand and its arguments after Git's global options."""

    index = 0
    while index < len(arguments) and arguments[index].startswith("-"):
        if arguments[index] in _GIT_VALUE_OPTIONS:
            index += 1
        index += 1
    if index >= len(arguments):
        return None, []
    return arguments[index], arguments[index + 1 :]


def _unstaged(cwd: str) -> bool:
    try:
        completed = subprocess.run(  # noqa: S603 -- fixed read-only Git argv, no shell
            ["git", "-C", cwd, "diff", "--name-only"],  # noqa: S607 -- the agent's own Git
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _git_verdict(subcommand: str, arguments: list[str]) -> str | None:
    long, short, positional = _flags(arguments)
    if subcommand == "stash":
        return None if positional[:1] in (["list"], ["show"]) else "stash"
    if subcommand == "reset":
        return "destructive-reset" if "--hard" in long else None
    if subcommand == "restore":
        staged_only = ("--staged" in long or "S" in short) and not (
            "--worktree" in long or "W" in short
        )
        return None if staged_only else "destructive-restore"
    if subcommand == "clean":
        dry = "--dry-run" in long or "n" in short
        return None if dry else "destructive-restore"
    if subcommand == "checkout":
        if "--" in arguments or "." in positional or "--force" in long or "f" in short:
            return "destructive-restore"
        return None
    if subcommand == "switch":
        forced = {"--force", "--discard-changes", "--force-create"} & long
        return "destructive-restore" if forced or {"f", "C"} & short else None
    if subcommand == "push":
        forced = {"--force", "--force-with-lease", "--force-if-includes"} & long
        plus = any(word.startswith("+") for word in positional[1:])
        return "force-push" if forced or "f" in short or plus else None
    if subcommand == "merge":
        return "direct-merge"
    if subcommand == "rebase":
        return "direct-rebase"
    if subcommand == "worktree":
        action = positional[:1]
        if action == ["remove"]:
            return "direct-workspace-removal"
        return "direct-workspace-creation" if action in (["add"], ["move"]) else None
    if subcommand == "branch":
        delete = "--delete" in long or "d" in short
        force = "--force" in long or "f" in short
        return "direct-workspace-removal" if "D" in short or (delete and force) else None
    return None


def _wt_verdict(arguments: list[str]) -> str | None:
    index = 0
    while index < len(arguments) and arguments[index].startswith("-"):
        if arguments[index] in {"-C", "--config"}:
            index += 1
        index += 1
    rest = arguments[index:]
    if not rest:
        return None
    if rest[0] == "merge":
        return "direct-merge"
    if rest[0] == "remove":
        return "direct-workspace-removal"
    if rest[0] == "step" and len(rest) > 1 and rest[1] in {"rebase", "push"}:
        return "direct-rebase"
    if rest[0] == "switch":
        long, short, _ = _flags(rest[1:])
        if "--create" in long or "c" in short:
            return "direct-workspace-creation"
    return None


_UNBOUNDED = {".", "./", "..", "../", "*", "./*", "~", "~/", "~/*", "/", "/*"}
_HOME_WORDS = {"$HOME", "${HOME}", "$HOME/", "${HOME}/", "$HOME/*", "${HOME}/*"}


def _rm_verdict(arguments: list[str]) -> str | None:
    long, short, targets = _flags(arguments)
    recursive = "--recursive" in long or "r" in short or "R" in short
    force = "--force" in long or "f" in short
    if not (recursive and force):
        return None
    home = os.path.realpath(os.path.expanduser("~"))
    for target in targets:
        if target in _UNBOUNDED or target in _HOME_WORDS:
            return "unbounded-delete"
        if target.startswith("/") and os.path.realpath(target) in {"/", home}:
            return "unbounded-delete"
    return None


_RUNNERS = {"uv", "uvx", "pipx", "poetry", "pdm", "hatch", "rye", "pre-commit"}


def _is_pre_commit(words: list[str]) -> bool:
    runner = _basename(words[0])
    if runner not in _RUNNERS and not runner.startswith("python"):
        return False
    for position, word in enumerate(words):
        if _basename(word) in {"pre-commit", "pre_commit"}:
            rest = [item for item in words[position + 1 :] if not item.startswith("-")]
            return not rest or rest[0] == "run"
    return False


def _shell_script(words: list[str]) -> str | None:
    for position, word in enumerate(words[1:], start=1):
        if word == "--":
            return None
        if not word.startswith("-"):
            return None
        if "c" in word[1:] and not word.startswith("--"):
            return words[position + 1] if position + 1 < len(words) else None
    return None


def classify(text: str, cwd: str, depth: int = 0) -> Verdict | None:
    if depth > 8:
        return None
    commands, nested = _parse(text)
    for script in nested:
        verdict = classify(script, cwd, depth + 1)
        if verdict is not None:
            return verdict
    for simple in commands:
        words = _unwrap(simple.words)
        if not words:
            continue
        name = _basename(words[0])
        shown = " ".join(words)
        if name == "cd" and len(words) > 1 and not words[1].startswith("-"):
            cwd = os.path.join(cwd, os.path.expanduser(words[1]))
            continue
        category = None
        if name in _SHELLS:
            script = _shell_script(words)
            if script is not None:
                verdict = classify(script, cwd, depth + 1)
                if verdict is not None:
                    return verdict
            elif len(words) == 1 or all(word.startswith("-") for word in words[1:]):
                for body in simple.heredocs:
                    verdict = classify(body, cwd, depth + 1)
                    if verdict is not None:
                        return verdict
            continue
        if name == "eval":
            verdict = classify(" ".join(words[1:]), cwd, depth + 1)
            if verdict is not None:
                return verdict
            continue
        if name == "git":
            subcommand, arguments = _git(words[1:])
            if subcommand is not None:
                category = _git_verdict(subcommand, arguments)
        elif name == "wt":
            category = _wt_verdict(words[1:])
        elif name == "rm":
            category = _rm_verdict(words[1:])
        if category is None and _is_pre_commit(words) and _unstaged(cwd):
            category = "pre-commit-dirty-tree"
        if category is not None:
            return Verdict(category, shown)
    return None


def _command(payload: object) -> tuple[str | None, str]:
    if not isinstance(payload, dict):
        return None, os.getcwd()
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
    tool_input = payload.get("tool_input")
    source = tool_input if isinstance(tool_input, dict) else payload
    for key in ("command", "command_line", "cmd"):
        value = source.get(key)
        if isinstance(value, str):
            return value, cwd
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return " ".join(_quote(item) for item in value), cwd
    return None, cwd


def _adopted(cwd: str) -> bool:
    """The rules apply only in a Git work tree whose root holds signetum.toml."""

    directory = os.path.abspath(cwd)
    while True:
        if os.path.exists(os.path.join(directory, ".git")):
            return os.path.isfile(os.path.join(directory, "signetum.toml"))
        parent = os.path.dirname(directory)
        if parent == directory:
            return False
        directory = parent


def _quote(word: str) -> str:
    return "'" + word.replace("'", "'\\''") + "'"


def main() -> int:
    try:
        command, cwd = _command(json.loads(sys.stdin.read()))
        if command is None or not _adopted(cwd):
            return 0
        verdict = classify(command, cwd)
    except Exception as error:  # a guard that cannot run allows the command
        print(
            json.dumps({"guard": "signetum", "status": "unavailable", "cause": repr(error)}),
            file=sys.stderr,
        )
        return 0
    if verdict is None:
        return 0
    print(
        json.dumps(
            {
                "guard": "signetum",
                "category": verdict.category,
                "use": USE[verdict.category],
                "command": verdict.command,
            }
        ),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
