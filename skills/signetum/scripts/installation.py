"""Installation-scoped guards and version storage, outside application repositories."""

import fcntl
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path


def data_root() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return base / "signetum"


@contextmanager
def entry_switch(entry: Path):
    """Lock one install entry without resolving or locking its version directory."""

    locks = data_root() / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(os.path.abspath(entry).encode()).hexdigest()
    with (locks / (key + ".entry.lock")).open("a") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Skill entry is being switched; retry the update") from error
        try:
            yield
        finally:
            fcntl.flock(guard, fcntl.LOCK_UN)


@contextmanager
def installation_use(root: Path, *, exclusive: bool = False):
    locks = data_root() / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()
    with (locks / (key + ".lock")).open("a") as guard:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(guard, mode | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "Skill installation is in use; retry the explicit update when idle"
            ) from error
        # The engine inherits the shared guard across exec; parallel uses stay shared.
        os.set_inheritable(guard.fileno(), True)
        try:
            yield
        finally:
            fcntl.flock(guard, fcntl.LOCK_UN)
