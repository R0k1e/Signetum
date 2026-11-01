"""Run one reviewed Skill engine without entering an application's environment."""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from shutil import which

if sys.version_info < (3, 12):  # noqa: UP036 -- bootstrap runs before engine environment
    raise SystemExit("Signetum needs host Python 3.12+; prepare it with the declared Mise setup.")

import tomllib

SKILL = Path(__file__).resolve().parents[1]
PROJECT = SKILL / "scripts/engine"
sys.path.insert(0, str(PROJECT))
from signetum.commands import BOOTSTRAP  # noqa: E402 -- dependency-free registry
from signetum.runtime_identity import implementation_digest  # noqa: E402 -- source identity only


def environment() -> dict[str, str]:
    result = dict(os.environ)
    for name in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONHOME"):
        result.pop(name, None)
    return result


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments:
        arguments = ["--help"]
    if len(arguments) == 2 and arguments[0] in BOOTSTRAP and arguments[1] == "--help":
        print(json.dumps({"command": arguments[0], "help": BOOTSTRAP[arguments[0]]}))
        return 0
    if arguments == ["update"] or arguments == ["update", "--help"]:
        print(
            json.dumps(
                {
                    "status": "instructions",
                    "operation": "update",
                    "instructions": str(SKILL / "references/adoption.md"),
                    "steps": [
                        "Acquire the full Skill at an exact revision into a separate directory.",
                        "Run setup and identity; verify help and required project commands.",
                        "If the engine changed, preview/apply bindings in a change workspace."
                        " Qualify and deliver the update.",
                        "Select the verified installation; remove the old copy only when unused.",
                    ],
                    "automatic_updates": False,
                },
                sort_keys=True,
            )
        )
        return 0
    code = implementation_digest()
    lock = (PROJECT / "uv.lock").read_bytes()
    content = code.encode() + lock + (PROJECT / "pyproject.toml").read_bytes()
    fingerprint = hashlib.sha256(content).hexdigest()
    cache = SKILL / ".runtime"
    if cache.is_symlink():
        raise ValueError("Skill runtime directory cannot be a symlink")
    home = cache / fingerprint
    if home.is_symlink():
        raise ValueError("Skill engine environment cannot be a symlink")
    python = home / "environment/bin/python"
    receipt = home / "installed.json"
    child = environment()
    if arguments == ["setup"]:
        home.mkdir(parents=True, exist_ok=True)
        with (cache / "setup.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX)
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
            observed = subprocess.check_output(  # noqa: S603 -- absolute prepared engine
                [str(python), "-I", "-m", "signetum.runtime_identity"], env=environment(), text=True
            )
            identity = json.loads(observed)
            if identity["implementation"] != code:
                raise ValueError("installed engine content differs from the Skill source")
            temporary = receipt.with_suffix(".pending")
            temporary.write_text(
                json.dumps({"environment": fingerprint, "engine": identity}, sort_keys=True)
            )
            os.replace(temporary, receipt)
            bootstrap = cache / "host-python.pending"
            bootstrap.unlink(missing_ok=True)
            bootstrap.symlink_to(python)
            os.replace(bootstrap, cache / "host-python")
        print(
            json.dumps(
                {"status": "prepared", "environment": str(home), "engine": identity}, sort_keys=True
            )
        )
        return 0
    if not python.is_file() or not receipt.is_file():
        raise ValueError("Skill environment is not prepared; run the explicit setup command first")
    recorded = json.loads(receipt.read_text())
    if recorded["environment"] != fingerprint:
        raise ValueError("Skill environment identity changed; explicitly prepare it again")
    observed = json.loads(
        subprocess.check_output(  # noqa: S603 -- absolute prepared engine
            [str(python), "-I", "-m", "signetum.runtime_identity"], env=child, text=True
        )
    )
    if observed != recorded["engine"] or observed["implementation"] != code:
        raise ValueError("Skill engine changed; ordinary execution will not repair or update it")
    if arguments == ["identity"]:
        complete = json.loads(
            subprocess.check_output(  # noqa: S603 -- verified engine and fixed identity module
                [str(python), "-I", "-m", "signetum.skill_identity", str(SKILL)],
                env=child,
                text=True,
            )
        )
        print(json.dumps({"skill": complete, "engine": observed}, sort_keys=True))
        return 0
    operation = arguments[0]
    if operation != "adopt" and (Path.cwd() / "signetum.toml").is_file():
        declared = tomllib.loads((Path.cwd() / "signetum.toml").read_text())
        if declared["signetum"].get("engine_digest") != code:
            raise ValueError(
                "project engine pin differs from this Skill; review an explicit update"
            )
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
