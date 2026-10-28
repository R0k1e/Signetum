"""Bound each validation command independently, including nested commands."""

import os
import signal
import subprocess  # nosec B404
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

if __name__ != "__main__":
    # The standalone supervisor does not import or execute the caller's package.
    from signetum.git import isolated_git_environment


def run_command(
    repository: Path,
    command: Sequence[str],
    *,
    timeout_seconds: float,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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
            env=isolated_git_environment(environment),
            start_new_session=True,
            pass_fds=(lease_read,),
        ) as process:
            os.close(lease_read)
            lease_read = -1
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(
                    command, timeout_seconds, output=stdout, stderr=stderr
                ) from None
            if process.returncode in (126, 127):
                raise OSError(f"validation command unavailable: {stderr.strip()}")
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        if lease_read >= 0:
            os.close(lease_read)
        os.close(lease_write)


def _watch_owner(lease: int) -> None:
    # Only the caller holds the write end. Its death closes the lease even
    # when an outer timeout kills it before it can run Python cleanup.
    try:
        while os.read(lease, 1):
            pass
        os.killpg(os.getpgrp(), signal.SIGKILL)
    finally:
        os.close(lease)


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) < 3 or arguments[1] != "--":
        return 126
    lease = int(arguments[0])
    threading.Thread(target=_watch_owner, args=(lease,), daemon=True).start()
    try:
        # Keep the supervisor alive so its lease watcher can clean this group.
        # The command inherits neither end of the lease.
        result = subprocess.call(arguments[2:])  # noqa: S603  # nosec B603
        return result if result >= 0 else 128 - result
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 127 if isinstance(error, FileNotFoundError) else 126


if __name__ == "__main__":
    raise SystemExit(main())
