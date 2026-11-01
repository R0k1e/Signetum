"""Install the latest stable Skill, with optional checks and exact targets."""

from __future__ import annotations

import argparse
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
from pathlib import Path, PurePosixPath

from installation import data_root, entry_switch

ENTRY = Path(__file__).absolute().parents[1]
SKILL = ENTRY.resolve()
sys.path.insert(0, str(SKILL / "scripts/engine"))
from signetum.skill_identity import (  # noqa: E402 -- stdlib-only content owner
    content_digest,
    skill_files,
)

REPOSITORY = "R0k1e/Signetum"
API = "https://api.github.com/repos/" + REPOSITORY
MAX_ARCHIVE = 32 * 1024 * 1024


def _read(url: str) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {
        "api.github.com",
        "github.com",
        "codeload.github.com",
    }:
        raise ValueError("update acquisition requires a declared GitHub HTTPS origin")
    request = urllib.request.Request(  # noqa: S310 -- exact HTTPS origin checked above
        url,
        headers={"User-Agent": "Signetum-explicit-update", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed HTTPS origins
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


def latest_release() -> dict[str, str] | None:
    releases = json.loads(_read(API + "/releases?per_page=100"))
    eligible: list[dict[str, str]] = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        asset = next(
            (a for a in release.get("assets", []) if a["name"] == "release-source.json"), None
        )
        if asset is None:
            continue
        url = asset["browser_download_url"]
        if not url.startswith("https://github.com/" + REPOSITORY + "/releases/download/"):
            raise ValueError("release metadata is outside the declared repository")
        raw = json.loads(_read(url))
        metadata = raw.get("release", raw)
        components = metadata.get("components", [])
        component = next((c for c in components if c.get("name") == "signetum-skill"), None)
        if component is None:
            continue  # Historical RepoSeal releases are not Signetum upgrades.
        version, digest = component["version"], component["digest"]
        _version(version)
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise ValueError("release Skill identity is malformed")
        source = metadata["source"]
        if re.fullmatch(r"[0-9a-f]{40}", source) is None:
            raise ValueError("release source is not an exact commit")
        eligible.append({"version": version, "content_digest": digest, "source": source})
    return max(eligible, key=lambda item: _version(item["version"])) if eligible else None


def check(current: Path, source: Path | None) -> dict[str, object]:
    installed = describe(current)
    candidate = describe(source) if source is not None else latest_release()
    if candidate is None:
        return {"status": "no_release", "current": installed, "candidate": None}
    if installed["content_digest"] == candidate["content_digest"]:
        status = "current"
    elif _version(candidate["version"]) < _version(installed["version"]):
        status = "ahead"
    else:
        status = "available"
    return {"status": status, "current": installed, "candidate": candidate}


def _extract(payload: bytes, destination: Path) -> Path:
    root = destination / "skill"
    root.mkdir()
    written = set()
    total = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            parts = path.parts
            if len(parts) < 4 or parts[1:3] != ("skills", "signetum"):
                continue
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                raise ValueError("update archive contains an escaping path")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("update archive contains a symlink")
            relative = Path(*parts[3:])
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
    describe(root)
    return root


def _remote_source(ref: str, destination: Path) -> tuple[Path, str]:
    if re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+|[0-9a-f]{40}", ref) is None:
        raise ValueError("--to requires an exact commit or release version, not a moving branch")
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", ref):
        ref = "v" + ref
    commit = json.loads(_read(API + "/commits/" + urllib.parse.quote(ref, safe="")))["sha"]
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("update source did not resolve to an exact commit")
    payload = _read("https://codeload.github.com/" + REPOSITORY + "/zip/" + commit)
    return _extract(payload, destination), commit


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
    if not (root / ".runtime/host-python").exists():
        _invoke(root, "setup", cwd=state)
    identity = _invoke(root, "identity", cwd=state)
    expected = describe(root)
    if identity.get("skill") != expected:
        raise ValueError("prepared Skill identity differs from its complete source")
    engine = identity.get("engine")
    if not isinstance(engine, dict) or engine.get("version") != expected["version"]:
        raise ValueError("prepared engine and Skill versions differ")
    return identity


def _version_copy(source: Path, state: Path) -> Path:
    digest = describe(source)["content_digest"].removeprefix("sha256:")
    versions = state / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    target = versions / digest / "signetum"
    if target.exists():
        if target.is_symlink() or describe(target) != describe(source):
            raise ValueError("existing version storage differs from the requested source")
        return target
    with tempfile.TemporaryDirectory(prefix="acquire-", dir=versions) as temporary:
        stage = Path(temporary) / "signetum"
        stage.mkdir()
        for path in skill_files(source):
            output = stage / path.relative_to(source)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
        if describe(stage) != describe(source):
            raise ValueError("source changed while acquiring the complete Skill")
        target.parent.mkdir()
        os.replace(stage, target)
    return target


def _refuse_protected_target(entry: Path) -> None:
    """A symlink entry may move. Source checkouts and version storage may not."""

    if entry.is_symlink():
        return
    versions = data_root() / "versions"
    if versions.exists():
        try:
            entry.resolve().relative_to(versions.resolve())
        except ValueError:
            protected_version = False
        else:
            protected_version = True
        if protected_version:
            raise ValueError("update refuses to rewrite a version directory")
    executable = shutil.which("git")
    if executable is None:
        return
    completed = subprocess.run(  # noqa: S603 -- resolved Git executable, explicit argv, no shell
        [executable, "-C", str(entry), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0 and completed.stdout.strip() == "true":
        raise ValueError("update refuses to overwrite a Git-managed source directory")


def install(entry: Path, source: Path, project: Path) -> dict[str, object]:
    _refuse_protected_target(entry)
    current = entry.resolve()
    _invoke(current, "identity", cwd=project)
    before, requested = describe(current), describe(source)
    if before == requested:
        return {"status": "current", "current": before, "entry": str(entry)}
    state = data_root()
    state.mkdir(parents=True, exist_ok=True)
    candidate = _version_copy(source, state)
    identity = _prepare(candidate, state)
    manifest = project / "signetum.toml"
    if manifest.exists():
        snapshot = manifest.read_bytes()
        try:
            _invoke(candidate, "check", "manifest", "--manifest", str(manifest), cwd=project)
        except ValueError as error:
            return {
                "status": "migration_required",
                "cause": str(error),
                "candidate_entry": str(candidate),
                "current": before,
            }
        if manifest.read_bytes() != snapshot:
            raise ValueError("project configuration changed during compatibility inspection")
    try:
        current.resolve().relative_to((state / "versions").resolve())
    except ValueError:
        retained = _version_copy(current, state)
    else:
        retained = current
    if retained.resolve() != current.resolve():
        # Version copies omit .runtime. Prepare that new path once so the
        # retained installation stays executable. An in-place version directory
        # keeps its existing environment and is not prepared again.
        _prepare(retained, state)
    with entry_switch(entry):
        if entry.resolve() != current:
            raise ValueError("Skill entry changed while starting the update; inspect and retry")
        temporary = entry.with_name("." + entry.name + ".next-" + uuid.uuid4().hex)
        backup = entry.with_name("." + entry.name + ".previous-" + uuid.uuid4().hex)
        temporary.symlink_to(candidate, target_is_directory=True)
        moved = False
        try:
            if not entry.is_symlink():
                os.replace(entry, backup)
                moved = True
            os.replace(temporary, entry)
        except OSError:
            if moved:
                os.replace(backup, entry)
            raise
        finally:
            temporary.unlink(missing_ok=True)
        if moved:
            shutil.rmtree(backup)
    return {
        "status": "updated",
        "current": identity,
        "entry": str(entry),
        "previous_entry": str(retained),
        "project_changed": False,
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Read-only local-source or stable-release check"
    )
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--source", type=Path, help="Explicit complete local Skill directory")
    sources.add_argument("--to", help="Explicit release tag/version or immutable commit")
    args = parser.parse_args(arguments)
    try:
        if args.check:
            if args.to:
                raise ValueError("--check accepts --source or checks stable releases")
            result = check(SKILL, args.source)
        elif args.source:
            result = install(ENTRY, args.source.resolve(), Path.cwd())
        else:
            state = data_root()
            state.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="download-", dir=state) as temporary:
                if args.to:
                    source, commit = _remote_source(args.to, Path(temporary))
                else:
                    candidate = latest_release()
                    if candidate is None:
                        raise ValueError("no stable Signetum release is available")
                    installed = describe(SKILL)
                    same = installed["content_digest"] == candidate["content_digest"]
                    newer = _version(candidate["version"]) > _version(installed["version"])
                    if same or not newer:
                        source = None
                        result = {
                            "status": "current",
                            "current": installed,
                            "candidate": candidate,
                            "entry": str(ENTRY),
                            "project_changed": False,
                        }
                    else:
                        source, commit = _remote_source(candidate["source"], Path(temporary))
                if source is not None:
                    result = {**install(ENTRY, source, Path.cwd()), "source": commit}
        result = {"schema_version": 1, "operation": "update", **result}
        print(json.dumps(result, sort_keys=True))
        return 2 if result["status"] == "migration_required" else 0
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
