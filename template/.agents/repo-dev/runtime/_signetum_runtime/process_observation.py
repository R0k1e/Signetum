# Generated from signetum.validation.process_observation; edit the engine source and regenerate.
"""Observe job ownership without engine imports or application dependencies.

Linux uses procfs. Darwin uses its public libproc metadata and KERN_PROCARGS2
interface. Environment contents never leave this module; only matching random
owner tokens and process identities are exposed to the settlement owner.
"""

import ctypes
import errno
import json
import os
import re
import shutil
import signal
import stat
import struct
import sys
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

OWNER_ENV = "SIGNETUM_PROCESS_OWNERS"
SCRATCH_ENV = "SIGNETUM_PROCESS_SCRATCH"
JOB_SCRATCH_ENV = "SIGNETUM_JOB_SCRATCH"


class ProcessObservationUnavailable(OSError):
    """The host cannot establish process ownership with its declared adapter."""


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    session: int
    started: int
    uid: int
    zombie: bool


@dataclass(frozen=True)
class OwnedProcess:
    identity: ProcessIdentity
    ownership: str


@dataclass(frozen=True)
class OwnershipScan:
    owned: tuple[OwnedProcess, ...]
    unavailable: tuple[int, ...]
    uninspected: int = 0


@dataclass(frozen=True)
class ScratchRoot:
    path: Path
    device: int
    inode: int
    owner: str


def verify_scratch_root(root: ScratchRoot) -> None:
    """A path string alone never authorizes a process or directory removal."""
    try:
        identity = root.path.lstat()
        if (
            not stat.S_ISDIR(identity.st_mode)
            or identity.st_uid != os.getuid()
            or stat.S_IMODE(identity.st_mode) != 0o700
            or (identity.st_dev, identity.st_ino) != (root.device, root.inode)
            or root.path.resolve(strict=True) != root.path
            or re.fullmatch(r"[0-9a-f]{32}", root.owner) is None
            or not root.path.name.startswith(f"signetum-job-{root.owner}-")
        ):
            raise ProcessObservationUnavailable("registered scratch directory identity changed")
    except OSError as error:
        raise ProcessObservationUnavailable(
            "registered scratch directory is unavailable"
        ) from error


def create_scratch_root(owner: str, *, parent: Path | None = None) -> ScratchRoot:
    if re.fullmatch(r"[0-9a-f]{32}", owner) is None:
        raise ValueError("scratch creation requires an exact owner token")
    path = Path(tempfile.mkdtemp(prefix=f"signetum-job-{owner}-", dir=parent)).resolve()
    identity = path.stat()
    root = ScratchRoot(path, identity.st_dev, identity.st_ino, owner)
    verify_scratch_root(root)
    return root


def encode_scratch_root(root: ScratchRoot) -> str:
    verify_scratch_root(root)
    return json.dumps(
        {"path": str(root.path), "device": root.device, "inode": root.inode, "owner": root.owner}
    )


def decode_scratch_root(value: str, owner: str) -> ScratchRoot:
    try:
        data = json.loads(value)
        if (
            not isinstance(data, dict)
            or set(data) != {"path", "device", "inode", "owner"}
            or not isinstance(data["path"], str)
            or type(data["device"]) is not int
            or type(data["inode"]) is not int
            or data["owner"] != owner
        ):
            raise ValueError("invalid scratch identity")
        root = ScratchRoot(Path(data["path"]), data["device"], data["inode"], owner)
        verify_scratch_root(root)
        return root
    except (ValueError, TypeError) as error:
        raise ProcessObservationUnavailable("registered scratch identity is invalid") from error


def scratch_contains(root: ScratchRoot, path: Path) -> bool:
    verify_scratch_root(root)
    # Native cwd observations are absolute kernel paths. Normalizing the
    # observed path prevents a child symlink from claiming an unrelated tree.
    return path.is_absolute() and path.resolve().is_relative_to(root.path)


def remove_scratch_root(root: ScratchRoot) -> None:
    verify_scratch_root(root)
    shutil.rmtree(root.path)


def owner_tokens(value: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(value)
    except ValueError:
        return ()
    if not isinstance(decoded, list) or any(
        not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{32}", item) is None for item in decoded
    ):
        return ()
    return tuple(dict.fromkeys(decoded))


def _environment_tokens(values: tuple[bytes, ...]) -> tuple[str, ...]:
    matches = [
        value.partition(b"=")[2]
        for value in values
        if value.partition(b"=")[0] == OWNER_ENV.encode()
    ]
    if len(matches) != 1:
        return ()
    try:
        return owner_tokens(matches[0].decode("ascii"))
    except UnicodeDecodeError:
        return ()


class _BSDInfo(ctypes.Structure):
    # Public proc_bsdinfo layout from sys/proc_info.h. No private SDK or
    # development headers are required by the installed runtime.
    _fields_ = (
        [
            (name, ctypes.c_uint32)
            for name in (
                "flags",
                "status",
                "xstatus",
                "pid",
                "ppid",
                "uid",
                "gid",
                "ruid",
                "rgid",
                "saved_uid",
                "saved_gid",
                "reserved",
            )
        ]
        + [("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32)]
        + [
            (name, ctypes.c_uint32)
            for name in ("files", "group", "job_count", "device", "tty_group")
        ]
        + [
            ("nice", ctypes.c_int32),
            ("start_seconds", ctypes.c_uint64),
            ("start_microseconds", ctypes.c_uint64),
        ]
    )
    pid: int
    status: int
    uid: int
    start_seconds: int
    start_microseconds: int


@lru_cache(maxsize=1)
def _libproc() -> ctypes.CDLL:
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_listpids.argtypes = (
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_int,
    )
    library.proc_listpids.restype = ctypes.c_int
    library.proc_pidinfo.argtypes = (
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    )
    library.proc_pidinfo.restype = ctypes.c_int
    return library


def _darwin_pids() -> tuple[int, ...]:
    library = _libproc()
    for _ in range(3):
        required = library.proc_listpids(1, 0, None, 0)
        if required <= 0:
            raise ProcessObservationUnavailable("native process inventory is unavailable")
        buffer = (ctypes.c_int * (required // ctypes.sizeof(ctypes.c_int) + 128))()
        received = library.proc_listpids(1, 0, buffer, ctypes.sizeof(buffer))
        if received <= 0:
            raise ProcessObservationUnavailable("native process inventory is unavailable")
        if received < ctypes.sizeof(buffer):
            return tuple(
                pid for pid in buffer[: received // ctypes.sizeof(ctypes.c_int)] if pid > 0
            )
    raise ProcessObservationUnavailable("native process inventory changed beyond its snapshot")


def _darwin_identity(pid: int) -> ProcessIdentity:
    info = _BSDInfo()
    size = ctypes.sizeof(info)
    if _libproc().proc_pidinfo(pid, 3, 0, ctypes.byref(info), size) != size or info.pid != pid:
        raise OSError(ctypes.get_errno() or errno.ESRCH, "process metadata unavailable")
    return ProcessIdentity(
        pid,
        os.getsid(pid),
        info.start_seconds * 1_000_000 + info.start_microseconds,
        info.uid,
        info.status == 5,
    )


def _darwin_environment(pid: int) -> tuple[bytes, ...]:
    library = ctypes.CDLL(None, use_errno=True)
    query = library.sysctl
    query.argtypes = (
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    )
    query.restype = ctypes.c_int
    key = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2, pid
    size = ctypes.c_size_t()
    if query(key, 3, None, ctypes.byref(size), None, 0) or size.value < 4:
        raise OSError(ctypes.get_errno() or errno.ESRCH, "process arguments unavailable")
    buffer = ctypes.create_string_buffer(size.value)
    if query(key, 3, buffer, ctypes.byref(size), None, 0):
        raise OSError(ctypes.get_errno() or errno.ESRCH, "process arguments unavailable")
    data = buffer.raw[: size.value]
    try:
        argc = struct.unpack_from("i", data)[0]
        if argc < 0 or argc > len(data):
            raise ValueError("invalid argument count")
        position = data.index(b"\0", 4) + 1
        while position < len(data) and data[position] == 0:
            position += 1
        for _ in range(argc):
            position = data.index(b"\0", position) + 1
        return tuple(data[position:].split(b"\0"))
    except (ValueError, struct.error) as error:
        raise ProcessObservationUnavailable("native argument snapshot is invalid") from error


def _linux_identity(pid: int, root: Path = Path("/proc")) -> ProcessIdentity:
    directory = root / str(pid)
    stat = (directory / "stat").read_text()
    if stat.partition(" ")[0] != str(pid):
        raise ProcessObservationUnavailable("procfs snapshot names another process")
    fields = stat.rpartition(") ")[2].split()
    try:
        return ProcessIdentity(
            pid, int(fields[3]), int(fields[19]), directory.stat().st_uid, fields[0] == "Z"
        )
    except (IndexError, ValueError) as error:
        raise ProcessObservationUnavailable("procfs process snapshot is invalid") from error


def process_identity(pid: int) -> ProcessIdentity:
    if sys.platform == "darwin":
        return _darwin_identity(pid)
    if sys.platform.startswith("linux"):
        return _linux_identity(pid)
    raise ProcessObservationUnavailable(f"unsupported process observation host: {sys.platform}")


def process_owner_tokens(pid: int) -> tuple[str, ...]:
    if sys.platform == "darwin":
        values = _darwin_environment(pid)
    elif sys.platform.startswith("linux"):
        values = tuple((Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0"))
    else:
        raise ProcessObservationUnavailable(f"unsupported process observation host: {sys.platform}")
    return _environment_tokens(values)


class _VnodeStat(ctypes.Structure):
    # Fixed-width public vinfo_stat, not the platform-dependent libc stat.
    _fields_ = (
        [
            ("device", ctypes.c_uint32),
            ("mode", ctypes.c_uint16),
            ("links", ctypes.c_uint16),
            ("inode", ctypes.c_uint64),
            ("uid", ctypes.c_uint32),
            ("gid", ctypes.c_uint32),
        ]
        + [
            (name, ctypes.c_int64)
            for name in (
                "accessed",
                "accessed_ns",
                "modified",
                "modified_ns",
                "changed",
                "changed_ns",
                "born",
                "born_ns",
                "size",
                "blocks",
            )
        ]
        + [("block_size", ctypes.c_int32)]
        + [(name, ctypes.c_uint32) for name in ("flags", "generation", "raw_device")]
        + [("reserved", ctypes.c_int64 * 2)]
    )


class _VnodeInfo(ctypes.Structure):
    _fields_ = (
        ("stat", _VnodeStat),
        ("type", ctypes.c_int),
        ("pad", ctypes.c_int),
        ("filesystem", ctypes.c_int32 * 2),
    )


class _VnodeInfoPath(ctypes.Structure):
    _fields_ = (("info", _VnodeInfo), ("path", ctypes.c_char * 1024))
    path: bytes


class _VnodePathInfo(ctypes.Structure):
    _fields_ = (("cwd", _VnodeInfoPath), ("root", _VnodeInfoPath))
    cwd: _VnodeInfoPath


def process_cwd(pid: int) -> Path:
    if sys.platform.startswith("linux"):
        return Path(os.readlink(Path("/proc") / str(pid) / "cwd"))
    if sys.platform == "darwin":
        info = _VnodePathInfo()
        size = ctypes.sizeof(info)
        if _libproc().proc_pidinfo(pid, 9, 0, ctypes.byref(info), size) != size:
            raise OSError(ctypes.get_errno() or errno.ESRCH, "process cwd unavailable")
        if not info.cwd.path:
            raise ProcessObservationUnavailable("native cwd snapshot is empty")
        return Path(os.fsdecode(info.cwd.path))
    raise ProcessObservationUnavailable(f"unsupported process observation host: {sys.platform}")


def _process_pids() -> tuple[int, ...]:
    if sys.platform == "darwin":
        return _darwin_pids()
    if sys.platform.startswith("linux"):
        return tuple(int(path.name) for path in Path("/proc").iterdir() if path.name.isdecimal())
    raise ProcessObservationUnavailable(f"unsupported process observation host: {sys.platform}")


def observe_owned_processes(
    owner: str, session: int, scratch: ScratchRoot | None = None
) -> OwnershipScan:
    """Protect the job root and observer; inspect only this user's environments."""
    if re.fullmatch(r"[0-9a-f]{32}", owner) is None or session <= 0:
        raise ValueError("process observation requires an exact owner token and positive session")
    if scratch is not None:
        verify_scratch_root(scratch)
        if scratch.owner != owner:
            raise ProcessObservationUnavailable("scratch belongs to a different job")
    pids = _process_pids()
    unavailable = []
    uninspected = 0
    root_start = None
    try:
        root = process_identity(session)
        root_owned = (
            not root.zombie and root.session == session and owner in process_owner_tokens(session)
        )
        if root_owned:
            root_start = root.started
    except OSError:
        root_owned = False
        try:
            os.kill(session, 0)
        except ProcessLookupError:
            pass
        except PermissionError:
            unavailable.append(session)
        else:
            unavailable.append(session)
    found = []
    for pid in pids:
        if pid in {os.getpid(), session}:
            continue
        try:
            identity = process_identity(pid)
        except OSError:
            # A process may exit during enumeration. If the kernel still
            # identifies an owned session member, incomplete metadata is visible.
            try:
                if root_owned and os.getsid(pid) == session:
                    unavailable.append(pid)
                else:
                    uninspected += 1
            except ProcessLookupError:
                pass
            except OSError:
                uninspected += 1
            continue
        if identity.zombie:
            continue
        # A job cannot own a process born before its verified root. This avoids
        # reading long-running unrelated applications' environment blocks.
        if root_start is not None and identity.started < root_start:
            continue
        if root_owned and identity.session == session:
            try:
                # A session number may be recycled after its root exits.
                # The target's own birth identity cannot prove root identity.
                root_owned = process_identity(session) == root
            except OSError:
                root_owned = False
        if root_owned and identity.session == session:
            found.append(OwnedProcess(identity, "session"))
        elif identity.uid == os.getuid():
            matched = False
            try:
                if owner in process_owner_tokens(pid):
                    found.append(OwnedProcess(identity, "owner-token"))
                    matched = True
            except OSError:
                # Unreadable unrelated environments establish no ownership and
                # never authorize cleanup. Known session members use metadata.
                uninspected += 1
            if scratch is not None and not matched:
                try:
                    if scratch_contains(scratch, process_cwd(pid)):
                        found.append(OwnedProcess(identity, "scratch-cwd"))
                except OSError:
                    uninspected += 1
    return OwnershipScan(
        tuple(sorted(found, key=lambda item: item.identity.pid)), tuple(unavailable), uninspected
    )


@dataclass(frozen=True)
class ProcessSettlement:
    leaked: tuple[int, ...]
    remaining: tuple[int, ...]
    unavailable: tuple[int, ...]


def settle_owned_processes(
    owner: str, session: int, scratch: ScratchRoot | None = None
) -> ProcessSettlement:
    """Bound cleanup and recheck birth identity before each destructive signal."""
    leaked: set[int] = set()
    unavailable: set[int] = set()
    # TERM allows ordinary shutdown. Repeated inventories also catch children
    # created during shutdown; KILL is bounded and never targets a bare PID.
    for termination_signal, duration in ((signal.SIGTERM, 0.2), (signal.SIGKILL, 0.3)):
        deadline = time.monotonic() + duration
        while True:
            scan = observe_owned_processes(owner, session, scratch)
            unavailable.update(scan.unavailable)
            if not scan.owned:
                return ProcessSettlement(tuple(sorted(leaked)), (), tuple(sorted(unavailable)))
            for process in scan.owned:
                identity = process.identity
                leaked.add(identity.pid)
                try:
                    current = process_identity(identity.pid)
                    if current != identity or current.zombie:
                        continue
                    os.kill(identity.pid, termination_signal)
                except ProcessLookupError:
                    pass
                except OSError:
                    unavailable.add(identity.pid)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.02)
    final = observe_owned_processes(owner, session, scratch)
    unavailable.update(final.unavailable)
    return ProcessSettlement(
        tuple(sorted(leaked)),
        tuple(process.identity.pid for process in final.owned),
        tuple(sorted(unavailable)),
    )
