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
    observer = _observer()
    encoded = os.environ.get(observer.SCRATCH_ENV)
    scratch = observer.decode_scratch_root(encoded, owner) if encoded is not None else None
    result = observer.settle_owned_processes(owner, session, scratch)
    if scratch is not None and not result.remaining and not result.unavailable:
        observer.remove_scratch_root(scratch)
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
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    observer = _observer()
    owner = uuid.uuid4().hex
    child_environment = isolated_git_environment(environment)
    enclosing = observer.owner_tokens(child_environment.get(observer.OWNER_ENV, "[]"))
    encoded_parent = child_environment.get(observer.SCRATCH_ENV)
    parent = (
        observer.decode_scratch_root(encoded_parent, enclosing[-1]).path
        if enclosing and encoded_parent is not None
        else None
    )
    scratch = observer.create_scratch_root(owner, parent=parent)
    child_environment[observer.OWNER_ENV] = json.dumps([*enclosing, owner])
    child_environment[observer.SCRATCH_ENV] = observer.encode_scratch_root(scratch)
    child_environment[observer.JOB_SCRATCH_ENV] = str(scratch.path)
    lease_read, lease_write = os.pipe()
    session = None
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
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=child_environment,
            start_new_session=True,
            pass_fds=(lease_read,),
        ) as process:
            session = process.pid
            os.close(lease_read)
            lease_read = -1
            try:
                stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
            except BaseException as error:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                settled = observer.settle_owned_processes(owner, process.pid, scratch)
                if not settled.remaining and not settled.unavailable:
                    observer.remove_scratch_root(scratch)
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
        # Normal supervisors remove their scratch after settlement. If launch
        # failed or the supervisor was killed, retain any unverified residue.
        if scratch.path.exists():
            try:
                scan = (
                    observer.observe_owned_processes(owner, session, scratch)
                    if session is not None
                    else None
                )
                if scan is None or (not scan.owned and not scan.unavailable):
                    observer.remove_scratch_root(scratch)
            except OSError as error:
                print(f"process scratch retained: {scratch.path}: {error}", file=sys.stderr)


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
