"""Standalone pre-push guard for Git's negotiated old and proposed new identity."""

import os
import subprocess  # nosec B404 -- preserve the executable repository hook without a shell
import sys
from pathlib import Path


def main() -> int:
    expected_ref, expected_base, expected_new, original, *arguments = sys.argv[1:]
    data = sys.stdin.buffer.read()
    rows = [line.split() for line in data.decode().splitlines() if line.strip()]
    if (
        len(rows) != 1
        or len(rows[0]) != 4
        or rows[0][1:]
        != [
            expected_new,
            expected_ref,
            expected_base,
        ]
    ):
        print(
            "remote delivery branch changed during publication; "
            "synchronize the batch and rerun final",
            file=sys.stderr,
        )
        return 1
    if Path(original).is_file() and os.access(original, os.X_OK):
        return subprocess.run(  # noqa: S603  # nosec B603 -- existing executable hook, no shell
            [original, *arguments], input=data, check=False
        ).returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
