"""Run one reviewed Skill engine without entering an application's environment."""

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from shutil import which

from installation import runtime_root, runtime_use

if sys.version_info < (3, 12):  # noqa: UP036 -- bootstrap runs before engine environment
    raise SystemExit("Signetum needs host Python 3.12+; prepare it with the declared Mise setup.")


SKILL = Path(__file__).resolve().parents[1]
PROJECT = SKILL / "scripts/engine"
# The one place the Skill's Worktrunk version is pinned; the launcher reads it for Mise too.
WORKTRUNK_PIN = SKILL / "scripts/worktrunk-version"
sys.path.insert(0, str(PROJECT))
from signetum.commands import BOOTSTRAP  # noqa: E402 -- dependency-free registry
from signetum.runtime_identity import implementation_digest  # noqa: E402 -- source identity only


def environment() -> dict[str, str]:
    result = dict(os.environ)
    for name in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONHOME"):
        result.pop(name, None)
    return result


def _observe(python: Path) -> dict[str, object]:
    return json.loads(
        subprocess.check_output(  # noqa: S603 -- absolute prepared engine
            [str(python), "-I", "-B", "-m", "signetum.runtime_identity"],
            env=environment(),
            text=True,
        )
    )


def _worktrunk_version(executable: Path) -> str:
    completed = subprocess.run(  # noqa: S603 -- absolute recorded executable, fixed argv
        [str(executable), "--version"],
        env=environment(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    version = completed.stdout.strip()
    if completed.returncode or not version:
        raise ValueError(f"Worktrunk at {executable} did not report its version")
    return version


def _provided_worktrunk() -> dict[str, str]:
    """The pinned Worktrunk Mise put on PATH for setup, as an absolute executable and version."""

    pin = WORKTRUNK_PIN.read_text().strip()
    found = which("wt")
    if found is None:
        raise ValueError("Worktrunk is missing; run setup through the Skill launcher")
    executable = Path(found).resolve()
    version = _worktrunk_version(executable)
    if re.search(rf"(?<![\d.]){re.escape(pin)}(?![\d.])", version) is None:
        raise ValueError(f"Worktrunk {version} is not the pinned {pin}")
    return {"path": str(executable), "version": version, "pin": pin}


def _prepared(
    home: Path, fingerprint: str, code: str
) -> tuple[dict[str, object], dict[str, str]] | None:
    """Return the recorded engine and Worktrunk identities when this environment is intact."""

    python = home / "environment/bin/python"
    receipt = home / "installed.json"
    if not python.is_file() or not receipt.is_file():
        return None
    recorded = json.loads(receipt.read_text())
    if recorded.get("environment") != fingerprint:
        raise ValueError("Skill environment identity changed; explicitly prepare it again")
    observed = _observe(python)
    if observed != recorded.get("engine") or observed["implementation"] != code:
        raise ValueError("Skill engine changed; ordinary execution will not repair or update it")
    worktrunk = recorded.get("worktrunk")
    if (
        not isinstance(worktrunk, dict)
        or not isinstance(worktrunk.get("path"), str)
        or worktrunk.get("pin") != WORKTRUNK_PIN.read_text().strip()
    ):
        raise ValueError("Skill Worktrunk is not recorded; explicitly prepare it again")
    path = Path(worktrunk["path"])
    if not path.is_file() or _worktrunk_version(path) != worktrunk.get("version"):
        raise ValueError("Skill Worktrunk changed; ordinary execution will not repair or update it")
    return observed, {key: str(value) for key, value in worktrunk.items()}


def _prepare(home: Path, fingerprint: str, code: str) -> tuple[dict[str, object], dict[str, str]]:
    worktrunk = _provided_worktrunk()
    home.mkdir(parents=True, exist_ok=True)
    child = environment()
    child["UV_PROJECT_ENVIRONMENT"] = str(home / "environment")
    uv = which("uv")
    if uv is None:
        raise ValueError("uv is missing; prepare the declared host tools before setup")
    subprocess.run(  # noqa: S603 -- explicit locked Skill setup
        [
            uv,
            "sync",
            "--project",
            str(PROJECT),
            "--locked",
            "--no-dev",
            "--no-editable",
            "--python",
            sys.executable,
        ],
        env=child,
        check=True,
        timeout=600,
    )
    identity = _observe(home / "environment/bin/python")
    if identity["implementation"] != code:
        raise ValueError("installed engine content differs from the Skill source")
    receipt = home / "installed.json"
    temporary = receipt.with_suffix(".pending")
    temporary.write_text(
        json.dumps(
            {"environment": fingerprint, "engine": identity, "worktrunk": worktrunk},
            sort_keys=True,
        )
    )
    os.replace(temporary, receipt)
    return identity, worktrunk


def _link_bootstrap(cache: Path, python: Path) -> None:
    """Point the shared bootstrap interpreter at a prepared environment."""

    pending = cache / ("host-python." + uuid.uuid4().hex + ".pending")
    pending.symlink_to(python)
    os.replace(pending, cache / "host-python")


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments:
        arguments = ["--help"]
    if len(arguments) == 2 and arguments[0] in BOOTSTRAP and arguments[1] == "--help":
        print(json.dumps({"command": arguments[0], "help": BOOTSTRAP[arguments[0]]}))
        return 0
    code = implementation_digest()
    lock = (PROJECT / "uv.lock").read_bytes()
    content = (
        code.encode()
        + lock
        + (PROJECT / "pyproject.toml").read_bytes()
        + WORKTRUNK_PIN.read_bytes()
    )
    fingerprint = hashlib.sha256(content).hexdigest()
    cache = runtime_root()
    home = cache / fingerprint
    if home.is_symlink():
        raise ValueError("Skill engine environment cannot be a symlink")
    python = home / "environment/bin/python"
    if arguments == ["setup"]:
        try:
            with runtime_use(fingerprint):
                prepared = _prepared(home, fingerprint, code)
        except ValueError:
            prepared = None
        if prepared is None:
            with runtime_use(fingerprint, exclusive=True):
                prepared = _prepare(home, fingerprint, code)
        _link_bootstrap(cache, python)
        print(
            json.dumps(
                {
                    "status": "prepared",
                    "environment": str(home),
                    "engine": prepared[0],
                    "worktrunk": prepared[1],
                },
                sort_keys=True,
            )
        )
        return 0
    with runtime_use(fingerprint):
        prepared = _prepared(home, fingerprint, code)
        if prepared is None:
            raise ValueError(
                "Skill environment is not prepared; run the explicit setup command first"
            )
        observed, worktrunk = prepared
        child = environment()
        # The engine runs this Worktrunk instead of resolving wt through the project.
        child["SIGNETUM_WORKTRUNK"] = worktrunk["path"]
        # Status explains how to enable the guard for the host that loads this Skill.
        child["SIGNETUM_SKILL"] = str(SKILL)
        if arguments == ["identity"]:
            complete = json.loads(
                subprocess.check_output(  # noqa: S603 -- verified engine and fixed identity module
                    [str(python), "-I", "-B", "-m", "signetum.skill_identity", str(SKILL)],
                    env=child,
                    text=True,
                )
            )
            print(
                json.dumps(
                    {"skill": complete, "engine": observed, "worktrunk": worktrunk},
                    sort_keys=True,
                )
            )
            return 0
        os.execve(  # noqa: S606 -- absolute verified Skill executable
            str(home / "environment/bin/signetum"),
            [str(home / "environment/bin/signetum"), *arguments],
            child,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(
            json.dumps(
                {"status": "failed", "stage": "skill-execution", "cause": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
