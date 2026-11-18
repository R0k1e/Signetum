"""Where Claude Code and Codex read user Skills and hooks, and the guard entry Signetum owns.

Standard library only: the distribution script loads it before an engine environment
exists, and status uses it to explain how to enable the guard.
"""

from __future__ import annotations

import copy
import json
import os
import shlex
from pathlib import Path
from typing import Any

HOSTS = ("claude", "codex")
GUARD = "scripts/command-guard"
# The guard runs before tools; the same script's notice mode runs at session start.
EVENTS = ("PreToolUse", "SessionStart")
# Any Signetum guard entry, wherever its Skill copy lives, ends with this path.
GUARD_MARK = "signetum/" + GUARD
PROJECT_CONFIGS = {
    "claude": (".claude/settings.json", ".claude/settings.local.json"),
    "codex": (".codex/hooks.json",),
}

JsonObject = dict[str, Any]


def host_home(host: str) -> Path:
    if host == "claude":
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    if host == "codex":
        return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    raise ValueError(f"unknown host {host}; use one of {', '.join(HOSTS)}")


def skills_dir(host: str) -> Path:
    return host_home(host) / "skills"


def hook_config(host: str) -> Path:
    """The user-level file each host reads hook entries from."""

    return host_home(host) / ("settings.json" if host == "claude" else "hooks.json")


def guard_entry(skill: Path) -> JsonObject:
    command = "/bin/sh " + shlex.quote(str(skill / GUARD))
    return {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": command, "timeout": 10}],
    }


def session_entry(skill: Path) -> JsonObject:
    command = "/bin/sh " + shlex.quote(str(skill / GUARD)) + " session-start"
    return {"hooks": [{"type": "command", "command": command, "timeout": 10}]}


def entries(skill: Path) -> dict[str, JsonObject]:
    """The hook entry this Skill's copy registers for each event."""

    return {"PreToolUse": guard_entry(skill), "SessionStart": session_entry(skill)}


def read_config(path: Path) -> JsonObject:
    """A host configuration document; an absent file is empty, a malformed one is refused."""

    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError(f"{path} must hold a JSON object")
    hooks = document.get("hooks", {})
    if not isinstance(hooks, dict) or any(
        not isinstance(hooks.get(event, []), list) for event in EVENTS
    ):
        raise ValueError(f"{path} hooks must be an object of event lists")
    return document


def _commands(document: JsonObject, event: str) -> list[str]:
    hooks = document.get("hooks", {})
    groups = hooks.get(event, []) if isinstance(hooks, dict) else []
    return [
        hook["command"]
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("hooks"), list)
        for hook in group["hooks"]
        if isinstance(hook, dict) and isinstance(hook.get("command"), str)
    ]


def runs_guard(document: JsonObject, skill: Path) -> bool:
    """Whether both the guard and the session notice run this Skill's script."""

    paths = {str(skill / GUARD), str(skill.resolve() / GUARD)}
    return all(
        any(path in command for command in _commands(document, event) for path in paths)
        for event in EVENTS
    )


def without_guard(document: JsonObject) -> JsonObject:
    """The document with every Signetum guard hook removed and nothing else changed."""

    result = copy.deepcopy(document)
    hooks = result.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        return result
    for event in EVENTS:
        if not isinstance(hooks.get(event), list):
            continue
        kept = []
        for group in hooks[event]:
            listed = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(listed, list):
                kept.append(group)
                continue
            remaining = [
                hook
                for hook in listed
                if not (isinstance(hook, dict) and GUARD_MARK in str(hook.get("command", "")))
            ]
            if remaining or len(remaining) == len(listed):
                kept.append({**group, "hooks": remaining})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del result["hooks"]
    return result


def with_guard(document: JsonObject, skill: Path) -> JsonObject:
    """The document running exactly this Skill's guard and notice once each.

    Already-current input is returned.
    """

    wanted = entries(skill)
    hooks = document.get("hooks", {})
    current = all(
        isinstance(hooks, dict)
        and wanted[event] in hooks.get(event, [])
        and sum(GUARD_MARK in command for command in _commands(document, event)) == 1
        for event in EVENTS
    )
    if current:
        return document
    result = without_guard(document)
    revised = result.setdefault("hooks", {})
    if not isinstance(revised, dict):
        raise ValueError("hook configuration must be an object of event lists")
    for event in EVENTS:
        groups = revised.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError("hook configuration must be an object of event lists")
        groups.append(wanted[event])
    return result


def host_of(skill: Path) -> str | None:
    """The host whose user skills directory holds this Skill, if any."""

    parent = skill.resolve().parent
    for host in HOSTS:
        if parent == skills_dir(host).resolve():
            return host
    return None


def guard_notice(skill: Path, project: Path) -> JsonObject | None:
    """How to enable the guard when this Skill's host runs no hook for it; never a refusal."""

    host = host_of(skill)
    if host is None:
        return None
    for path in (hook_config(host), *(project / name for name in PROJECT_CONFIGS[host])):
        try:
            if runs_guard(read_config(path), skill):
                return None
        except (OSError, ValueError):
            continue
    launcher = shlex.quote(str(skill / "scripts/signetum"))
    return {
        "host": host,
        "configured": False,
        "enable": f"sh {launcher} install --host {host}",
        "config": str(hook_config(host)),
        "hook": {"hooks": {event: [entry] for event, entry in entries(skill).items()}},
        "note": "Optional: refuses work-losing commands early; operations work without it.",
    }
