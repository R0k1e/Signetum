"""Install and update the Signetum Skill folder and register its optional command guard."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from installation import data_root

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts/engine"))
from signetum import hosts  # noqa: E402 -- stdlib-only host configuration owner
from signetum.skill_identity import (  # noqa: E402 -- stdlib-only content owner
    content_digest,
    skill_files,
)

REPOSITORY = "R0k1e/Signetum"
LATEST = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
DOWNLOAD = f"https://github.com/{REPOSITORY}/releases/download/"
ORIGINS = {"github.com", "api.github.com"}
MAX_ARCHIVE = 32 * 1024 * 1024
PLUGIN = "signetum@signetum"
ARCHIVE_ROOT = "signetum"


def _read(url: str) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in ORIGINS:
        raise ValueError("release acquisition requires a declared GitHub HTTPS origin")
    request = urllib.request.Request(  # noqa: S310 -- exact HTTPS origin checked above
        url, headers={"User-Agent": "Signetum-explicit-update"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed origins
        if urllib.parse.urlsplit(response.geturl()).scheme != "https":
            raise ValueError("release acquisition cannot redirect to insecure transport")
        payload = response.read(MAX_ARCHIVE + 1)
    if len(payload) > MAX_ARCHIVE:
        raise ValueError("release download exceeds the bounded size")
    return payload


def _version(value: str) -> tuple[int, ...]:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is None:
        raise ValueError("Signetum version must be an explicit semantic version")
    return tuple(int(part) for part in value.split("."))


def describe(root: Path) -> dict[str, str]:
    required = ("SKILL.md", "scripts/signetum", "scripts/launch.py", "scripts/engine/uv.lock")
    if not all((root / name).is_file() for name in required):
        raise ValueError(f"{root} is not a complete Signetum Skill")
    project = tomllib.loads((root / "scripts/engine/pyproject.toml").read_text())["project"]
    if project["name"] != "signetum":
        raise ValueError(f"{root} is not the Signetum execution project")
    version = project["version"]
    _version(version)
    return {"version": version, "content_digest": content_digest(root)}


def _environment() -> dict[str, str]:
    result = dict(os.environ)
    for name in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONHOME"):
        result.pop(name, None)
    return result


def _inside_git(path: Path) -> bool:
    """Whether the nearest existing directory at or above path is inside a Git work tree."""

    git = shutil.which("git")
    existing = next((p for p in (path, *path.parents) if p.is_dir()), None)
    if git is None or existing is None:
        return False
    completed = subprocess.run(  # noqa: S603 -- resolved Git executable, explicit argv, no shell
        [git, "-C", str(existing), "rev-parse", "--is-inside-work-tree"],
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


# Published releases ------------------------------------------------------------------


def _tag(requested: str) -> str:
    if requested == "latest":
        tag = json.loads(_read(LATEST)).get("tag_name")
    else:
        tag = requested if requested.startswith("v") else "v" + requested
    if not isinstance(tag, str) or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) is None:
        raise ValueError("release tag is not an exact Signetum version")
    return tag


def _checksums(payload: bytes) -> dict[str, str]:
    sums = {}
    for line in payload.decode().splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            sums[PurePosixPath(name.lstrip("*")).name] = digest.lower()
    return sums


def _verified(sums: dict[str, str], name: str, payload: bytes) -> bytes:
    if sums.get(name) != hashlib.sha256(payload).hexdigest():
        raise ValueError(f"{name} differs from the release checksums")
    return payload


def released(requested: str = "latest") -> dict[str, str] | None:
    """The published release's Skill identity, bound to its checksums and source metadata."""

    try:
        tag = _tag(requested)
        sums = _checksums(_read(DOWNLOAD + tag + "/SHA256SUMS"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    version = tag[1:]
    raw = _verified(sums, "release-source.json", _read(DOWNLOAD + tag + "/release-source.json"))
    document = json.loads(raw)
    metadata = document.get("release", document)
    component = next(
        (c for c in metadata.get("components", []) if c.get("name") == "signetum-skill"), None
    )
    if component is None or component.get("version") != version:
        raise ValueError("release metadata differs from its tag")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", str(component.get("digest"))) is None:
        raise ValueError("release Skill identity is malformed")
    archive = f"signetum-skill-{version}.zip"
    if archive not in sums:
        raise ValueError("release checksums omit the Skill archive")
    return {
        "version": version,
        "content_digest": component["digest"],
        "tag": tag,
        "source": str(metadata.get("source")),
        "archive": archive,
    }


def _extract(payload: bytes, destination: Path) -> Path:
    root = destination / ARCHIVE_ROOT
    root.mkdir()
    written = set()
    total = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                raise ValueError("Skill archive contains an escaping path")
            if len(path.parts) < 2 or path.parts[0] != ARCHIVE_ROOT or item.is_dir():
                continue
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Skill archive contains a symlink")
            relative = Path(*path.parts[1:])
            if relative in written:
                raise ValueError("Skill archive contains a duplicate file")
            written.add(relative)
            total += item.file_size
            if total > MAX_ARCHIVE:
                raise ValueError("expanded Skill exceeds the bounded size")
            output = root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as stream:
                stream.write(archive.read(item))
            if item.external_attr >> 16 & 0o111:
                output.chmod(0o755)
    return root


def _download(candidate: dict[str, str], destination: Path) -> Path:
    tag, archive = candidate["tag"], candidate["archive"]
    sums = _checksums(_read(DOWNLOAD + tag + "/SHA256SUMS"))
    root = _extract(_verified(sums, archive, _read(DOWNLOAD + tag + "/" + archive)), destination)
    expected = {"version": candidate["version"], "content_digest": candidate["content_digest"]}
    if describe(root) != expected:
        raise ValueError("downloaded Skill differs from its release metadata")
    return root


# Skill folders -----------------------------------------------------------------------


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
    state.mkdir(parents=True, exist_ok=True)
    _invoke(root, "setup", cwd=state)
    identity = _invoke(root, "identity", cwd=state)
    expected = describe(root)
    if identity.get("skill") != expected:
        raise ValueError("prepared Skill identity differs from its complete source")
    engine = identity.get("engine")
    if not isinstance(engine, dict) or engine.get("version") != expected["version"]:
        raise ValueError("prepared engine and Skill versions differ")
    return identity


def _place(target: Path, source: Path) -> None:
    """Put a verified copy at target through a staged sibling and two renames."""

    token = uuid.uuid4().hex
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_name("." + target.name + ".next-" + token)
    backup = target.with_name("." + target.name + ".previous-" + token)
    try:
        for path in skill_files(source):
            output = stage / path.relative_to(source)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
        if describe(stage) != describe(source):
            raise ValueError("staged Skill differs from its source")
        if target.exists():
            os.replace(target, backup)
        try:
            os.replace(stage, target)
        except OSError:
            if backup.exists():
                os.replace(backup, target)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)


def _write_config(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".signetum-pending")
    pending.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(pending, path)


# Earlier plugin installs -------------------------------------------------------------


def _host(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- resolved host plugin manager, explicit argv, no shell
        argv, env=_environment(), capture_output=True, text=True, timeout=600, check=False
    )


def _plugins(host: str) -> list[dict[str, object]]:
    """The earlier signetum plugin installs this host reports, with how each is removed."""

    executable = shutil.which(host)
    if executable is None:
        return []
    if host == "claude":
        listed = _host([executable, "plugin", "list", "--json"])
        if listed.returncode:
            return [{"host": host, "status": "unknown", "cause": listed.stderr[-500:]}]
        found = []
        for entry in json.loads(listed.stdout or "[]"):
            if entry.get("id") != PLUGIN:
                continue
            scope = str(entry.get("scope", "user"))
            argv = ["plugin", "uninstall", PLUGIN, "--scope", scope]
            command = f"{host} {' '.join(argv)}"
            item: dict[str, object] = {"host": host, "scope": scope, "command": command}
            if scope == "user":
                item["argv"] = [executable, *argv]
            else:
                item["project"] = entry.get("projectPath")
            found.append(item)
        return found
    listed = _host([executable, "plugin", "list"])
    if listed.returncode:
        return [{"host": host, "status": "unknown", "cause": listed.stderr[-500:]}]
    pattern = re.compile(r"^\s*" + re.escape(PLUGIN) + r"\s+installed\b")
    if not any(pattern.match(line) for line in listed.stdout.splitlines()):
        return []
    argv = ["plugin", "remove", PLUGIN]
    command = f"{host} {' '.join(argv)}"
    return [{"host": host, "scope": "user", "command": command, "argv": [executable, *argv]}]


# Install -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    skill: Path
    host: str | None = None

    @property
    def config(self) -> Path | None:
        return hosts.hook_config(self.host) if self.host else None


def _targets(arguments: argparse.Namespace) -> list[Target]:
    # Resolved paths: the hook names the same path the launcher later reports as its own.
    targets = [
        Target((hosts.skills_dir(host) / "signetum").resolve(), host) for host in arguments.host
    ]
    targets += [
        Target((Path(path).expanduser() / "signetum").resolve()) for path in arguments.skills_dir
    ]
    if not targets:
        raise ValueError("name at least one --host or --skills-dir target")
    unique: dict[Path, Target] = {}
    for target in targets:
        unique.setdefault(target.skill, target)
    return list(unique.values())


def _skill_action(target: Path, source: Path, *, removing: bool) -> str:
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_dir():
            raise ValueError(f"{target} is not a Skill folder; move it aside explicitly")
        installed = describe(target)
        if _inside_git(target):
            raise ValueError(
                f"{target} is inside a Git work tree; update it through that repository"
            )
        if removing:
            return "remove"
        if target.resolve() == source.resolve():
            return "unchanged"
        return "unchanged" if installed == describe(source) else "replace"
    if removing:
        return "absent"
    if _inside_git(target.parent):
        raise ValueError(
            f"{target.parent} is inside a Git work tree; install never edits a project"
        )
    return "place"


def _hook_plan(target: Target, *, removing: bool) -> tuple[str, dict[str, object] | None]:
    if target.config is None:
        return "none", None
    current = hosts.read_config(target.config)
    revised = hosts.without_guard(current) if removing else hosts.with_guard(current, target.skill)
    if revised == current:
        return "unchanged", None
    return ("remove" if removing else "add"), revised


def _source(arguments: argparse.Namespace, scratch: Path) -> tuple[Path, dict[str, str] | None]:
    if arguments.release is not None:
        candidate = released(arguments.release)
        if candidate is None:
            raise ValueError("no published Signetum release matches the request")
        return _download(candidate, scratch), candidate
    if arguments.source is None:
        return SKILL, None
    path = Path(arguments.source).expanduser().absolute()
    if path.is_file() and zipfile.is_zipfile(path):
        return _extract(path.read_bytes(), scratch), None
    return path, None


def install(arguments: argparse.Namespace) -> dict[str, object]:
    removing = arguments.remove
    targets = _targets(arguments)
    state = data_root()
    state.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="install-", dir=state) as temporary:
        source, candidate = (SKILL, None) if removing else _source(arguments, Path(temporary))
        identity = {} if removing else describe(source)
        plans = []
        for target in targets:
            skill = _skill_action(target.skill, source, removing=removing)
            hook, revised = _hook_plan(target, removing=removing)
            plans.append((target, skill, hook, revised))
        named = dict.fromkeys(target.host for target in targets if target.host)
        found = [] if removing else [item for host in named if host for item in _plugins(host)]
        plugins = [{k: v for k, v in item.items() if k != "argv"} for item in found]
        report = []
        for target, skill, hook, _ in plans:
            entry: dict[str, object] = {"skill": str(target.skill), "skill_action": skill}
            if target.host:
                entry.update(host=target.host, config=str(target.config), hook_action=hook)
            if hook == "add":
                entry["hook"] = hosts.guard_entry(target.skill)
            report.append(entry)
        changed = any(
            skill in {"place", "replace", "remove"} or hook in {"add", "remove"}
            for _, skill, hook, _ in plans
        ) or any("argv" in item for item in found)
        status = "removed" if removing else "installed"
        result: dict[str, object] = {
            "status": "previewed" if arguments.preview else status if changed else "unchanged",
            "source": {
                "path": None if candidate else str(source),
                "release": candidate["tag"] if candidate else None,
                **identity,
            },
            "targets": report,
        }
        if not removing:
            result["plugins"] = plugins
        if arguments.preview:
            return result
        placing = any(skill in {"place", "replace"} for _, skill, _, _ in plans)
        if placing:
            # Prepare the source first, so a placed copy shares a verified environment.
            result["prepared"] = _prepare(source, state).get("engine")
        for target, skill, _hook, revised in plans:
            if skill in {"place", "replace"}:
                _place(target.skill, source)
            elif skill == "remove":
                shutil.rmtree(target.skill)
            if revised is not None and target.config is not None:
                _write_config(target.config, revised)
        for item, reported in zip(found, plugins, strict=True):
            argv = item.get("argv")
            if isinstance(argv, list):
                completed = _host([str(part) for part in argv])
                reported["status"] = "removed" if completed.returncode == 0 else "failed"
                if completed.returncode:
                    reported["cause"] = (completed.stderr or completed.stdout)[-1000:]
            elif "command" in item:
                reported["status"] = "manual"
        result["restart_required"] = changed or any(p.get("status") == "removed" for p in plugins)
        result["codex_hook_review_required"] = any(
            target.host == "codex" and hook == "add" for target, _, hook, _ in plans
        )
        return result


# Update ------------------------------------------------------------------------------


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


def update(skill: Path, project: Path) -> dict[str, object]:
    if _inside_git(skill):
        raise ValueError(
            "Skill folder is inside a Git work tree; update it through that repository"
        )
    installed = describe(skill)
    candidate = released()
    if candidate is None:
        raise ValueError("no published Signetum release")
    if _candidate_status(installed, candidate) != "available":
        return {"status": "current", "current": installed, "candidate": candidate}
    state = data_root()
    state.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="download-", dir=state) as temporary:
        root = _download(candidate, Path(temporary))
        identity = _prepare(root, state)
        manifest = project / "signetum.toml"
        if manifest.exists():
            snapshot = manifest.read_bytes()
            try:
                _invoke(root, "check", "manifest", "--manifest", str(manifest), cwd=project)
            except ValueError as error:
                return {"status": "migration_required", "cause": str(error)}
            if manifest.read_bytes() != snapshot:
                raise ValueError("project configuration changed during compatibility inspection")
        _place(skill, root)
    replaced = _invoke(skill, "identity", cwd=project)
    if (
        replaced.get("skill") != describe(skill)
        or describe(skill)["content_digest"] != candidate["content_digest"]
    ):
        raise ValueError("replaced Skill identity differs from the verified release")
    return {
        "migration_guidance": [
            "Signetum 0.8 reads schema-5 configuration and schema-1 change records unchanged.",
            "In a member, set signetum.toml schema_version to 6; use schema_version 2 "
            "for new change records with approval actor, recorded_at and neutral statement.",
            "Do not rewrite historical journals or approvals; approval digests and owed "
            "ledgers are ignored. Pending observations remain visible in delivery review.",
            "Scope revisions need recording only. Run ready, then the complete final "
            "in an authorized integration batch; delivery still needs explicit authorization.",
        ],
        "status": "updated",
        "skill": str(skill),
        "current": installed,
        "candidate": candidate,
        "candidate_engine": identity.get("engine"),
        "restart_required": True,
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    installer = commands.add_parser("install", help="Place the Skill and register the guard.")
    installer.add_argument("--host", action="append", default=[], choices=hosts.HOSTS)
    installer.add_argument("--skills-dir", action="append", default=[])
    sources = installer.add_mutually_exclusive_group()
    sources.add_argument("--source", help="A Skill folder or signetum-skill-<version>.zip.")
    sources.add_argument("--release", help="A published tag such as v0.5.0, or latest.")
    sources.add_argument("--remove", action="store_true", help="Remove the guard and the Skill.")
    installer.add_argument("--preview", action="store_true", help="Report the plan only.")
    updater = commands.add_parser("update", help="Replace this Skill with the newest release.")
    updater.add_argument("--check", action="store_true", help="Read-only release comparison.")
    args = parser.parse_args(arguments)
    try:
        if args.operation == "install":
            result = install(args)
        elif args.check:
            result = check(SKILL)
        else:
            result = update(SKILL, Path.cwd())
        failed = result["status"] in {"migration_required", "failed"}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        status = "unavailable" if getattr(args, "check", False) else "failed"
        result, failed = {"status": status, "cause": str(error)}, True
    payload = {"schema_version": 1, "operation": args.operation, "project_changed": False, **result}
    print(json.dumps(payload, sort_keys=True))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
