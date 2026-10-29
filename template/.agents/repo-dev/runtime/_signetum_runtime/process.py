# Generated from signetum.validation.process; edit the engine source and regenerate.
"""Bound each validation command independently, including nested commands."""

import importlib
import json
import os
import signal
import subprocess  # nosec B404
import sys
import threading
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

if __name__ != "__main__":
    # The standalone supervisor does not import or execute the caller's package.
    from .git import isolated_git_environment


def _observer() -> ModuleType:
    if __package__:
        return importlib.import_module(".process_observation", __package__)
    # Standalone -I -S supervisor loads only its sibling stdlib helper.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return importlib.import_module("process_observation")


def _settle(owner: str, session: int) -> int:
    result = _observer().settle_owned_processes(owner, session)
    if result.leaked or result.remaining or result.unavailable:
        print(
            f"owned process leak: observed={result.leaked}, "
            f"remaining={result.remaining}, unavailable={result.unavailable}",
            file=sys.stderr,
            flush=True,
        )
        return 126 if result.unavailable else 1
    return 0


def run_command(
    repository: Path,
    command: Sequence[str],
    *,
    timeout_seconds: float,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    observer = _observer()
    owner = uuid.uuid4().hex
    child_environment = isolated_git_environment(environment)
    child_environment[observer.OWNER_ENV] = json.dumps(
        [*observer.owner_tokens(child_environment.get(observer.OWNER_ENV, "[]")), owner]
    )
    lease_read, lease_write = os.pipe()
    try:
        invocation = [
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).resolve()),
            str(lease_read),
            "--",
            *command,
        ]
        with subprocess.Popen(  # noqa: S603  # nosec B603
            invocation,
            cwd=repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=child_environment,
            start_new_session=True,
            pass_fds=(lease_read,),
        ) as process:
            os.close(lease_read)
            lease_read = -1
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
            except BaseException as error:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                observer.settle_owned_processes(owner, process.pid)
                stdout, stderr = process.communicate(timeout=3)
                if isinstance(error, subprocess.TimeoutExpired):
                    raise subprocess.TimeoutExpired(
                        command, timeout_seconds, output=stdout, stderr=stderr
                    ) from None
                raise
            if process.returncode in (126, 127):
                raise OSError(f"validation command unavailable: {stderr.strip()}")
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        if lease_read >= 0:
            os.close(lease_read)
        os.close(lease_write)


def _watch_owner(lease: int, owner: str) -> None:
    # Only the caller holds the write end. Its death closes the lease even
    # when an outer timeout kills it before it can run Python cleanup.
    try:
        while os.read(lease, 1):
            pass
        try:
            _settle(owner, os.getsid(0))
        finally:
            os.killpg(os.getpgrp(), signal.SIGKILL)
    finally:
        os.close(lease)


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) < 3 or arguments[1] != "--":
        return 126
    lease = int(arguments[0])
    observer = _observer()
    tokens = observer.owner_tokens(os.environ.get(observer.OWNER_ENV, "[]"))
    if not tokens:
        print("process owner token unavailable", file=sys.stderr)
        return 126
    owner = tokens[-1]
    threading.Thread(target=_watch_owner, args=(lease, owner), daemon=True).start()
    try:
        # Keep the supervisor alive so its lease watcher can clean this group.
        # The command inherits neither end of the lease.
        result = subprocess.call(arguments[2:])  # noqa: S603  # nosec B603
        result = result if result >= 0 else 128 - result
        try:
            settlement = _settle(owner, os.getsid(0))
        except OSError as error:
            print(f"process observation unavailable: {error}", file=sys.stderr)
            settlement = 126
        return result or settlement
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 127 if isinstance(error, FileNotFoundError) else 126


if __name__ == "__main__":
    raise SystemExit(main())
