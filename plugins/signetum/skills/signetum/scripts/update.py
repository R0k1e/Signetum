"""Upgrade the installed Signetum plugin through each host's plugin manager."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from shutil import which

from installation import data_root

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts/engine"))
from signetum.skill_identity import content_digest  # noqa: E402 -- stdlib-only content owner

REPOSITORY = "R0k1e/Signetum"
PLUGIN = "signetum@signetum"
MARKETPLACE = "signetum"
PIN = "https://raw.githubusercontent.com/" + REPOSITORY + "/main/.claude-plugin/marketplace.json"
SKILL_PATH = ("plugins", "signetum", "skills", "signetum")
MAX_ARCHIVE = 32 * 1024 * 1024
ORIGINS = {"github.com", "codeload.github.com", "raw.githubusercontent.com"}


def _read(url: str) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in ORIGINS:
        raise ValueError("update acquisition requires a declared GitHub HTTPS origin")
    request = urllib.request.Request(  # noqa: S310 -- exact HTTPS origin checked above
        url, headers={"User-Agent": "Signetum-explicit-update"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed origins
        if urllib.parse.urlsplit(response.geturl()).scheme != "https":
            raise ValueError("update acquisition cannot redirect to insecure transport")
        payload = response.read(MAX_ARCHIVE + 1)
    if len(payload) > MAX_ARCHIVE:
        raise ValueError("update source exceeds the bounded download size")
    return payload


def _version(value: str) -> tuple[int, ...]:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is None:
        raise ValueError("update version must be an explicit semantic version")
    return tuple(int(part) for part in value.split("."))


def describe(root: Path) -> dict[str, str]:
    required = ("SKILL.md", "scripts/signetum", "scripts/launch.py", "scripts/engine/uv.lock")
    if not all((root / name).is_file() for name in required):
        raise ValueError("update source is not a complete Signetum Skill")
    project = tomllib.loads((root / "scripts/engine/pyproject.toml").read_text())["project"]
    if project["name"] != "signetum":
        raise ValueError("update source is not the Signetum execution project")
    version = project["version"]
    _version(version)
    return {"version": version, "content_digest": content_digest(root)}


def released() -> dict[str, str] | None:
    """The plugin release pinned in the marketplace on main, bound to its release metadata."""

    try:
        document = json.loads(_read(PIN))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    entry = next((p for p in document.get("plugins", []) if p.get("name") == "signetum"), None)
    if entry is None:
        return None
    source = entry["source"]
    version, ref, commit = entry["version"], source["ref"], source["sha"]
    _version(version)
    if (
        source.get("source") != "git-subdir"
        or source.get("path") != "/".join(SKILL_PATH[:2])
        or ref != "v" + version
        or re.fullmatch(r"[0-9a-f]{40}", commit) is None
    ):
        raise ValueError("marketplace pin is not an exact Signetum release")
    raw = json.loads(
        _read(f"https://github.com/{REPOSITORY}/releases/download/{ref}/release-source.json")
    )
    metadata = raw.get("release", raw)
    component = next(
        (c for c in metadata.get("components", []) if c.get("name") == "signetum-skill"), None
    )
    if component is None or metadata.get("source") != commit or component["version"] != version:
        raise ValueError("release metadata differs from the marketplace pin")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", component["digest"]) is None:
        raise ValueError("release Skill identity is malformed")
    return {"version": version, "content_digest": component["digest"], "source": commit}


def _candidate_status(installed: dict[str, str], candidate: dict[str, str]) -> str:
    """Same digest is current; an older version is ahead; anything else can replace."""

    if installed["content_digest"] == candidate["content_digest"]:
        return "current"
    if _version(candidate["version"]) < _version(installed["version"]):
        return "ahead"
    return "available"


def check(current: Path) -> dict[str, object]:
    installed = describe(current)
    candidate = released()
    if candidate is None:
        return {"status": "no_release", "current": installed, "candidate": None}
    return {
        "status": _candidate_status(installed, candidate),
        "current": installed,
        "candidate": candidate,
    }


def _extract(payload: bytes, destination: Path) -> Path:
    root = destination / "skill"
    root.mkdir()
    written = set()
    total = 0
    width = len(SKILL_PATH) + 1
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            parts = path.parts
            if len(parts) <= width or parts[1:width] != SKILL_PATH:
                continue
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                raise ValueError("update archive contains an escaping path")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("update archive contains a symlink")
            relative = Path(*parts[width:])
            if item.is_dir():
                continue
            if relative in written:
                raise ValueError("update archive contains a duplicate file")
            written.add(relative)
            total += item.file_size
            if total > MAX_ARCHIVE:
                raise ValueError("expanded Skill exceeds the bounded download size")
            output = root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as stream:
                stream.write(archive.read(item))
            if item.external_attr >> 16 & 0o111:
                output.chmod(0o755)
    return root


def _download(candidate: dict[str, str], destination: Path) -> Path:
    payload = _read(f"https://codeload.github.com/{REPOSITORY}/zip/{candidate['source']}")
    root = _extract(payload, destination)
    expected = {"version": candidate["version"], "content_digest": candidate["content_digest"]}
    if describe(root) != expected:
        raise ValueError("downloaded Skill differs from its release metadata")
    return root


def _environment() -> dict[str, str]:
    result = dict(os.environ)
    for name in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONHOME"):
        result.pop(name, None)
    return result


def _invoke(root: Path, *arguments: str, cwd: Path) -> dict[str, object]:
    completed = subprocess.run(  # noqa: S603 -- explicit trusted complete Skill, fixed shell
        ["/bin/sh", str(root / "scripts/signetum"), *arguments],
        cwd=cwd,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=660,
        check=False,
    )
    if completed.returncode:
        raise ValueError((completed.stderr or completed.stdout)[-3000:])
    return json.loads(completed.stdout.splitlines()[-1])


def _prepare(root: Path, state: Path) -> dict[str, object]:
    _invoke(root, "setup", cwd=state)
    identity = _invoke(root, "identity", cwd=state)
    expected = describe(root)
    if identity.get("skill") != expected:
        raise ValueError("prepared Skill identity differs from its complete source")
    engine = identity.get("engine")
    if not isinstance(engine, dict) or engine.get("version") != expected["version"]:
        raise ValueError("prepared engine and Skill versions differ")
    return identity


def _host(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- resolved host plugin manager, explicit argv, no shell
        argv, cwd=cwd, env=_environment(), capture_output=True, text=True, timeout=600, check=False
    )


def _installed_hosts(project: Path) -> list[tuple[str, str]]:
    """Hosts whose plugin manager reports signetum@signetum installed."""

    hosts = []
    claude = which("claude")
    if claude is not None:
        listed = _host([claude, "plugin", "list", "--json"], project)
        if listed.returncode:
            raise ValueError("claude plugin list failed: " + listed.stderr[-1000:])
        if any(entry.get("id") == PLUGIN for entry in json.loads(listed.stdout or "[]")):
            hosts.append(("claude", claude))
    codex = which("codex")
    if codex is not None:
        listed = _host([codex, "plugin", "list"], project)
        if listed.returncode:
            raise ValueError("codex plugin list failed: " + listed.stderr[-1000:])
        pattern = re.compile(r"^\s*" + re.escape(PLUGIN) + r"\s+installed\b")
        if any(pattern.match(line) for line in listed.stdout.splitlines()):
            hosts.append(("codex", codex))
    return hosts


def _codex_config() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"


def _codex_user_enabled() -> bool | None:
    path = _codex_config()
    if not path.is_file():
        return None
    entry = tomllib.loads(path.read_text()).get("plugins", {}).get(PLUGIN, {})
    return entry.get("enabled") if isinstance(entry, dict) else None


def _keep_codex_disabled() -> bool:
    """codex plugin add enables the plugin for every project; restore a user's disable."""

    path = _codex_config()
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    header = f'[plugins."{PLUGIN}"]'
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        return False
    for index in range(start + 1, len(lines)):
        if lines[index].lstrip().startswith("["):
            break
        if re.fullmatch(r"\s*enabled\s*=\s*true\s*", lines[index]):
            lines[index] = "enabled = false\n"
            break
    revised = "".join(lines)
    expected = tomllib.loads(text)
    expected["plugins"][PLUGIN]["enabled"] = False
    if tomllib.loads(revised) != expected:
        return False
    temporary = path.with_name(path.name + ".signetum-pending")
    temporary.write_text(revised)
    os.replace(temporary, path)
    return True


def upgrade(candidate_root: Path, project: Path) -> dict[str, object]:
    state = data_root()
    identity = _prepare(candidate_root, state)
    manifest = project / "signetum.toml"
    if manifest.exists():
        snapshot = manifest.read_bytes()
        try:
            _invoke(candidate_root, "check", "manifest", "--manifest", str(manifest), cwd=project)
        except ValueError as error:
            return {"status": "migration_required", "cause": str(error)}
        if manifest.read_bytes() != snapshot:
            raise ValueError("project configuration changed during compatibility inspection")
    hosts = _installed_hosts(project)
    if not hosts:
        raise ValueError(
            f"no host has {PLUGIN} installed; install the plugin through Claude Code or Codex"
        )
    commands = {
        "claude": (("plugin", "marketplace", "update", MARKETPLACE), ("plugin", "update", PLUGIN)),
        "codex": (("plugin", "marketplace", "upgrade", MARKETPLACE), ("plugin", "add", PLUGIN)),
    }
    upgraded = []
    for name, executable in hosts:
        disabled = name == "codex" and _codex_user_enabled() is False
        ran = []
        for arguments in commands[name]:
            completed = _host([executable, *arguments], project)
            ran.append(" ".join((name, *arguments)))
            if completed.returncode:
                return {
                    "status": "failed",
                    "cause": f"{ran[-1]} failed: {(completed.stderr or completed.stdout)[-2000:]}",
                    "upgraded": upgraded,
                    "candidate_engine": identity.get("engine"),
                }
        host: dict[str, object] = {"host": name, "commands": ran}
        if disabled:
            host["user_disabled_kept"] = _keep_codex_disabled()
        upgraded.append(host)
    return {
        "status": "updated",
        "upgraded": upgraded,
        "candidate_engine": identity.get("engine"),
        "restart_required": True,
        "codex_hook_review_required": any(item["host"] == "codex" for item in upgraded),
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Read-only comparison with the released plugin pin"
    )
    args = parser.parse_args(arguments)
    try:
        if args.check:
            result = check(SKILL)
        else:
            installed = describe(SKILL)
            candidate = released()
            if candidate is None:
                raise ValueError("no released Signetum plugin is pinned on main")
            if _candidate_status(installed, candidate) != "available":
                result = {"status": "current", "current": installed, "candidate": candidate}
            else:
                state = data_root()
                state.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix="download-", dir=state) as temporary:
                    root = _download(candidate, Path(temporary))
                    outcome = upgrade(root, Path.cwd())
                result = {"current": installed, "candidate": candidate, **outcome}
        result = {"schema_version": 1, "operation": "update", "project_changed": False, **result}
        print(json.dumps(result, sort_keys=True))
        return 2 if result["status"] in {"migration_required", "failed"} else 0
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        status = "unavailable" if args.check else "failed"
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "operation": "update",
                    "status": status,
                    "cause": str(error),
                    "project_changed": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
