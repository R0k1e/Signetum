"""Review exact project bindings; execution stays in the installed Skill."""

import difflib
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess  # nosec B404 -- resolved tool argv, never a shell
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Literal

from signetum import __version__
from signetum.contract_values import FrozenContract
from signetum.git import git_output, repository_path
from signetum.manifest import parse_manifest
from signetum.operation_cli import OperationParser, utility_failure
from signetum.runtime_identity import implementation_digest
from signetum.serialization import contract_mapping, dataclass_from_mapping, load_json
from signetum.source_authority import source_path
from signetum.validation.repository import configured_validation


@dataclass(frozen=True, kw_only=True)
class Retirement(FrozenContract):
    path: str
    digest: str


@dataclass(frozen=True, kw_only=True)
class AdoptionRequest(FrozenContract):
    manifest: str
    retirements: tuple[Retirement, ...] = ()


@dataclass(frozen=True, kw_only=True)
class FileChange(FrozenContract):
    path: str
    before: str | None
    after: str | None
    before_mode: int | None = None


@dataclass(frozen=True, kw_only=True)
class AdoptionPlan(FrozenContract):
    schema_version: Literal[1]
    engine_version: str
    base: str
    request: AdoptionRequest
    files: tuple[FileChange, ...]


def plan_digest(plan: AdoptionPlan) -> str:
    data = json.dumps(contract_mapping(plan), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _repository_root(repository: Path) -> Path:
    root = repository.resolve()
    if Path(git_output(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("adoption requires the repository root, not a subdirectory")
    return root


_VERSION_PARTS = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def _tool_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603 -- resolved executable, fixed argv
            (executable, "--version"),
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode or not completed.stdout.strip():
        return None
    return completed.stdout.strip().splitlines()[0]


def _version_met(text: str | None, minimum: tuple[int, ...]) -> bool:
    if text is None:
        return False
    match = _VERSION_PARTS.search(text)
    if match is None:
        return False
    found = tuple(int(part) for part in match.groups() if part is not None)
    width = max(len(found), len(minimum))
    return found + (0,) * (width - len(found)) >= minimum + (0,) * (width - len(minimum))


def _tool_report(name: str) -> dict[str, object]:
    executable = which(name)
    version = _tool_version(executable) if executable is not None else None
    report: dict[str, object] = {"present": executable is not None, "version": version}
    if name == "git":
        report["floors"] = {
            "signetum_commands": {"minimum": "2.7", "met": _version_met(version, (2, 7))},
            "worktrunk_cleanup": {"minimum": "2.17", "met": _version_met(version, (2, 17))},
        }
    return report


def _uv_resolution() -> dict[str, object]:
    path_executable = which("uv")
    path_version = _tool_version(path_executable) if path_executable is not None else None
    mise = which("mise")
    mise_version = None
    if mise is not None:
        try:
            completed = subprocess.run(  # noqa: S603  # nosec B603 -- resolved Mise, fixed argv
                (mise, "exec", "--", "uv", "--version"),
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed is not None and completed.returncode == 0 and completed.stdout.strip():
            mise_version = completed.stdout.strip().splitlines()[0]
    return {
        "path": path_version,
        "mise": mise_version,
        "differs": bool(path_version and mise_version and path_version != mise_version),
    }


def inspect(repository: Path) -> dict[str, object]:
    repository = _repository_root(repository)
    candidates = (
        "AGENTS.md",
        "CLAUDE.md",
        "Justfile",
        "mise.toml",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "package-lock.json",
        "Cargo.toml",
        "signetum.toml",
    )
    return {
        "schema_version": 1,
        "operation": "adopt-inspect",
        "status": "inspected",
        "base": git_output(repository, "rev-parse", "HEAD"),
        "present": [
            name
            for name in candidates
            if (repository / name).is_file() or (repository / name).is_symlink()
        ],
        "tools": {name: _tool_report(name) for name in ("git", "uv", "mise", "wt")},
        "uv_resolution": _uv_resolution(),
        "engine_digest": implementation_digest(),
        "required": [
            "Reviewed command, input and delivery bindings in signetum.toml.",
            "A prepared compatible Skill; project instructions remain unchanged.",
        ],
        "next": "Prepare a binding request and review its exact preview. No project command ran.",
    }


def _payload(repository: Path, request: AdoptionRequest) -> dict[str, str | None]:
    manifest = parse_manifest(request.manifest)
    graph, _ = configured_validation(manifest)
    if not all(graph.gate(name).shards for name in ("member", "final")):
        raise ValueError("adoption requires nonempty member and final checks")
    if manifest.delivery is None:
        raise ValueError("declare delivery.branch in the reviewed manifest")
    git_output(repository, "check-ref-format", "--branch", manifest.delivery.branch)
    files: dict[str, str | None] = {"signetum.toml": request.manifest}
    inventory_root = ".agents/signetum/runtime/_signetum_runtime"
    inventory_path = (
        source_path(repository, inventory_root + "/runtime.toml") if request.retirements else None
    )
    owned: dict[str, str] = {}
    if inventory_path is not None and inventory_path.is_file():
        inventory = tomllib.loads(inventory_path.read_text())
        owned = {inventory_root + "/" + name: digest for name, digest in inventory["files"].items()}
    wrappers = {
        ".agents/signetum/run",
        ".agents/signetum/WORKFLOW.md",
        ".agents/signetum/repo.yaml",
        inventory_root + "/runtime.toml",
        *[
            ".agents/signetum/runtime/" + name + ".py"
            for name in ("protocol", "lifecycle", "maintenance", "traceability")
        ],
    }
    for retirement in request.retirements:
        if retirement.path in files or retirement.path not in {*owned, *wrappers}:
            raise ValueError("retirement must name one inventoried managed file")
        path = source_path(repository, retirement.path)
        if not path.is_file():
            raise ValueError("retirement target is absent")
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != retirement.digest or (
            retirement.path in owned and digest != owned[retirement.path]
        ):
            raise ValueError("managed file changed; preserve user work and review it explicitly")
        files[retirement.path] = None
    return files


def preview(repository: Path, request: AdoptionRequest) -> AdoptionPlan:
    repository = _repository_root(repository)
    base = git_output(repository, "rev-parse", "HEAD")
    files = _payload(repository, request)
    before = {
        name: source_path(repository, name).read_text()
        if source_path(repository, name).exists()
        else None
        for name in files
    }
    if git_output(repository, "rev-parse", "HEAD") != base:
        raise ValueError("source changed while preparing adoption")
    return AdoptionPlan(
        schema_version=1,
        engine_version=__version__,
        base=base,
        request=request,
        files=tuple(
            FileChange(
                path=name,
                before=before[name],
                after=value,
                before_mode=stat.S_IMODE(source_path(repository, name).stat().st_mode)
                if before[name] is not None
                else None,
            )
            for name, value in sorted(files.items())
        ),
    )


def apply(repository: Path, plan: AdoptionPlan, expected: str) -> dict[str, object]:
    repository = _repository_root(repository)
    if (
        plan.schema_version != 1
        or plan.engine_version != __version__
        or plan_digest(plan) != expected
    ):
        raise ValueError("adoption plan identity changed; review a fresh preview")
    common = repository_path(repository, "rev-parse", "--git-common-dir")
    with (common / "signetum-adoption.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "another adoption writer is active; retry after it finishes"
            ) from error
        if git_output(repository, "rev-parse", "HEAD") != plan.base:
            raise ValueError("adoption source changed; review a fresh preview")
        before = {f.path: f.before for f in plan.files}
        if plan.request.retirements and all(
            (
                source_path(repository, f.path).read_text()
                if source_path(repository, f.path).exists()
                else None
            )
            == f.after
            for f in plan.files
        ):
            return {
                "schema_version": 1,
                "status": "unchanged",
                "operation": "adopt-apply",
                "plan_digest": expected,
            }
        desired = _payload(repository, plan.request)
        if len(before) != len(plan.files) or {f.path: f.after for f in plan.files} != desired:
            raise ValueError("adoption payload differs from this engine; review a fresh preview")
        current = {}
        for item in plan.files:
            path = source_path(repository, item.path)
            current[item.path] = path.read_text() if path.exists() else None
        if all(current[f.path] == f.after for f in plan.files):
            return {
                "schema_version": 1,
                "status": "unchanged",
                "operation": "adopt-apply",
                "plan_digest": expected,
            }
        if any(
            current[f.path] != f.before
            or (
                f.before_mode is not None
                and stat.S_IMODE(source_path(repository, f.path).stat().st_mode) != f.before_mode
            )
            for f in plan.files
        ):
            raise ValueError(
                "adoption target changed; preserve local work and review a fresh preview"
            )
        written = []
        created = []
        try:
            for item in plan.files:
                path = source_path(repository, item.path)
                if item.before == item.after:
                    continue
                observed = path.read_text() if path.exists() else None
                if (
                    observed != item.before
                    or git_output(repository, "rev-parse", "HEAD") != plan.base
                ):
                    raise ValueError(
                        "source or target changed during adoption; inspect before retry"
                    )
                missing = []
                parent = path.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for directory in reversed(missing):
                    directory.mkdir()
                    created.append(directory)
                if item.after is None:
                    path.unlink()
                else:
                    _replace(path, item.after)
                    if item.before_mode is not None:
                        path.chmod(item.before_mode)
                written.append(item)
        except (OSError, ValueError):
            for item in reversed(written):
                path = source_path(repository, item.path)
                if item.before is None:
                    path.unlink()
                else:
                    _replace(path, item.before)
                    if item.before_mode is not None:
                        path.chmod(item.before_mode)
            for directory in reversed(created):
                directory.rmdir()
            raise
    return {
        "schema_version": 1,
        "status": "applied",
        "operation": "adopt-apply",
        "plan_digest": expected,
        "files": len(written),
        "next": "Review and commit through the existing process; verify a real change. "
        "No approval or readiness was created.",
    }


def _replace(path: Path, text: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix=".signetum-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(description=__doc__)
    parser.add_argument("operation", choices=["inspect", "preview", "apply"])
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--expected-plan")
    try:
        args = parser.parse_args(arguments)
        if args.operation == "inspect":
            if any((args.request, args.output, args.plan, args.expected_plan)):
                raise ValueError("inspect accepts only the repository")
            result = inspect(args.repository)
        elif args.operation == "preview":
            if args.request is None or args.output is None or args.plan or args.expected_plan:
                raise ValueError("preview requires --request and --output only")
            request = dataclass_from_mapping(
                AdoptionRequest, load_json(args.request.read_text()), use_defaults=True
            )
            plan = preview(args.repository, request)
            try:
                with args.output.open("x", encoding="utf-8") as output:
                    json.dump(contract_mapping(plan), output, ensure_ascii=False, sort_keys=True)
            except FileExistsError as error:
                raise ValueError(
                    f"preview file already exists: {args.output}; choose another --output"
                ) from error
            changes = [f for f in plan.files if f.before != f.after]
            result = {
                "schema_version": 1,
                "operation": "adopt-preview",
                "status": "proposal",
                "plan": str(args.output),
                "plan_digest": plan_digest(plan),
                "base": plan.base,
                "files": [
                    {
                        "path": f.path,
                        "action": "delete"
                        if f.after is None
                        else "create"
                        if f.before is None
                        else "replace",
                    }
                    for f in changes
                ],
                "binding_diff": {
                    f.path: "".join(
                        difflib.unified_diff(
                            (f.before or "").splitlines(True),
                            (f.after or "").splitlines(True),
                            fromfile=f.path,
                            tofile=f.path,
                        )
                    )
                    for f in changes
                    if not f.path.startswith(".agents/signetum/runtime/")
                },
                "next": "Review the plan; apply only the approved plan digest. "
                "No application command ran.",
            }
        else:
            if args.plan is None or args.expected_plan is None or args.request or args.output:
                raise ValueError("apply requires --plan and --expected-plan only")
            plan = dataclass_from_mapping(AdoptionPlan, load_json(args.plan.read_text()))
            result = apply(args.repository, plan, args.expected_plan)
    except (OSError, ValueError) as error:
        return utility_failure("adopt", error)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
