"""Installation state outside application repositories and the plugin directory."""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path


def data_root() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return Path(base) / "signetum"


def runtime_root() -> Path:
    """Locked engine environments, shared by every copy of the same engine source."""

    return data_root() / "runtime"


@contextmanager
def runtime_use(fingerprint: str, *, exclusive: bool = False):
    """Commands share one prepared environment; preparing it takes it exclusively."""

    root = runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / (fingerprint + ".lock")).open("a") as guard:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(guard, mode | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "Skill environment is in use; retry setup when other commands finish"
            ) from error
        # The engine inherits the shared guard across exec; parallel uses stay shared.
        os.set_inheritable(guard.fileno(), True)
        try:
            yield
        finally:
            fcntl.flock(guard, fcntl.LOCK_UN)
