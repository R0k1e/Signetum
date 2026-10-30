"""Review and apply portable protocol bindings without replacing application tools."""

import difflib
import fcntl
import hashlib
import json
import os
import shlex
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Literal

from yaml import YAMLError, safe_load

from signetum import __version__
from signetum.contract_values import FrozenContract
from signetum.git import git_output
from signetum.manifest import parse_manifest
from signetum.operation_cli import OperationParser, utility_failure
from signetum.runtime_generation import RUNTIME_DIRECTORY, is_runtime_cache, runtime_files
from signetum.serialization import contract_mapping, dataclass_from_mapping, load_json
from signetum.source_authority import source_path
from signetum.validation.repository import configured_validation

WORKFLOW = """# Repository development

Read the repository architecture and selected policies before planning. Use the
existing application environment and runner. Start isolated work with
`sh .agents/signetum/run workspace-open <branch> <exact-base>`; continue inside
the returned worktree. The delivery worktree is changed only by explicit delivery.

Run local utilities with `sh .agents/signetum/run protocol <command>`.
Read `current` before planning and consult relevant historical sources listed
there. Create one record with `change-open <name>`. Fill intent, observable
requirements, acceptance, scope and autonomy, then show its generated `view`.
Record actual owner confirmation of that exact contract before implementation.
Important architecture, process and security choices require an accepted decision
transaction in that contract. A standalone ADR is only for an independently
maintained cross-change authority; keep its reasoning once and reference it.
Ordinary implementation choices and command output create no extra document.

The agent authors records; the owner reviews outcomes and consequential choices.
Use `record`, `resolve` and `reconcile` for significant findings and accepted
clause edits. Do not maintain duplicate reports or command-by-command journals.
When behavior, responsibility, commands or prerequisites change, update affected
current architecture and usage instructions in the same change. Preserve reasons
in history; check the affected current authorities before ready.
Ordinary test output stays in logs. Run the repository's existing targeted checks;
`ready` binds the exact member tip. A diagnostic retry never clears first failure.

Named batch admission and continuation prepare and run static checks. `final`
checks the complete frozen batch. Show the generated review before requesting
explicit delivery. Passing validation never authorizes publication or delivery.
Preserve unrelated changes and original evidence. Do not hide deferred work.
"""
POINTER = "\nRead `.agents/signetum/WORKFLOW.md` for the adopted local development protocol.\n"


@dataclass(frozen=True, kw_only=True)
class AdoptionRequest(FrozenContract):
    manifest: str
    policy: str
    interpreter: tuple[str, ...] = ("python3",)


@dataclass(frozen=True, kw_only=True)
class FileChange(FrozenContract):
    path: str
    before: str | None
    after: str


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


def inspect(repository: Path) -> dict[str, object]:
    repository = _repository_root(repository)
    base = git_output(repository, "rev-parse", "HEAD")
    candidates = (
        "AGENTS.md",
        "Justfile",
        "mise.toml",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "package-lock.json",
        "Cargo.toml",
        "Cargo.lock",
        "signetum.toml",
        ".agents/signetum/repo.yaml",
    )
    return {
        "schema_version": 1,
        "operation": "adopt-inspect",
        "status": "inspected",
        "base": base,
        "present": [p for p in candidates if source_path(repository, p).is_file()],
        "tools": {name: which(name) is not None for name in ("git", "python3", "mise", "wt")},
        "local_launcher": source_path(repository, ".agents/signetum/run").is_file(),
        "required": [
            "A reviewed manifest naming existing checks, tools and inputs.",
            "Repository policy naming its actual delivery branch.",
            "An existing architecture entry; no application metadata is generated.",
            "Host Python >=3.12; Mise and Worktrunk for workspace operations.",
        ],
        "next": "Prepare a binding request, then run adopt preview; "
        "inspect executes no project commands.",
    }


def _payload(request: AdoptionRequest) -> dict[str, str]:
    manifest = parse_manifest(request.manifest)
    graph, _ = configured_validation(manifest)
    if not all(graph.gate(name).shards for name in ("member", "final")):
        raise ValueError("adoption requires nonempty member and final checks")
    policy = safe_load(request.policy)
    if not isinstance(policy, dict) or not isinstance(policy.get("delivery"), dict):
        raise ValueError("adoption policy requires the repository delivery branch")
    branch = policy["delivery"].get("branch")
    if not isinstance(branch, str) or not branch.strip():
        raise ValueError("adoption policy requires a nonempty delivery branch")
    if not request.interpreter or any(not p or "\n" in p for p in request.interpreter):
        raise ValueError("interpreter requires a literal nonempty argv")
    command = shlex.join(request.interpreter)
    runtime = ".agents/signetum/runtime"
    files = {
        str(RUNTIME_DIRECTORY / name): content.decode() for name, content in runtime_files().items()
    }
    for name, module in [
        ("protocol", "protocol_cli"),
        ("lifecycle", "lifecycle"),
        ("maintenance", "maintenance"),
        ("traceability", "traceability_cli"),
    ]:
        files[f"{runtime}/{name}.py"] = (
            '"""Run the repository-owned protocol implementation."""\n'
            "import sys\nfrom pathlib import Path\nsys.dont_write_bytecode = True\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
            f"from _signetum_runtime.{module} import main  # noqa: E402\n"
            'if __name__ == "__main__":\n    raise SystemExit(main())\n'
        )
    files[".agents/signetum/run"] = (
        "#!/bin/sh\nset -eu\n"
        'case "${1:-}" in\n'
        f'  protocol|maintenance) entry="$1"; shift; exec {command} {runtime}/"$entry".py "$@" ;;\n'
        f'  *) exec {command} {runtime}/lifecycle.py "$@" ;;\nesac\n'
    )
    files.update(
        {
            "signetum.toml": request.manifest,
            ".agents/signetum/repo.yaml": request.policy,
            ".agents/signetum/WORKFLOW.md": WORKFLOW,
        }
    )
    return files


def _targets(
    repository: Path, request: AdoptionRequest, before: dict[str, str | None]
) -> dict[str, str]:
    files = _payload(request)
    architecture = parse_manifest(request.manifest).repository.architecture
    if not source_path(repository, architecture).is_file():
        raise ValueError(f"declare an existing architecture entry first: {architecture}")
    git_output(
        repository, "check-ref-format", "--branch", safe_load(request.policy)["delivery"]["branch"]
    )
    agents = before.get("AGENTS.md") or ""
    files["AGENTS.md"] = agents if POINTER.strip() in agents else agents + POINTER
    return files


def preview(repository: Path, request: AdoptionRequest) -> AdoptionPlan:
    repository = _repository_root(repository)
    base = git_output(repository, "rev-parse", "HEAD")
    files = _payload(request)
    directory = source_path(repository, RUNTIME_DIRECTORY.as_posix())
    if directory.exists():
        extras = [
            p.relative_to(repository).as_posix()
            for p in directory.rglob("*")
            if p.is_file()
            and not is_runtime_cache(p)
            and p.relative_to(repository).as_posix() not in files
        ]
        if extras:
            raise ValueError(
                "unmanaged runtime files require explicit review: " + ", ".join(sorted(extras))
            )
    before = {}
    for name in (*files, "AGENTS.md"):
        path = source_path(repository, name)
        before[name] = path.read_text() if path.exists() else None
    files = _targets(repository, request, before)
    if git_output(repository, "rev-parse", "HEAD") != base:
        raise ValueError("source changed while preparing adoption")
    return AdoptionPlan(
        schema_version=1,
        engine_version=__version__,
        base=base,
        request=request,
        files=tuple(
            FileChange(path=p, before=before[p], after=s) for p, s in sorted(files.items())
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
    common = Path(git_output(repository, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repository / common
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
        desired = _targets(repository, plan.request, before)
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
        if any(current[f.path] != f.before for f in plan.files):
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
                _replace(path, item.after)
                written.append(item)
        except (OSError, ValueError):
            for item in reversed(written):
                path = source_path(repository, item.path)
                if item.before is None:
                    path.unlink()
                else:
                    _replace(path, item.before)
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
            with args.output.open("x", encoding="utf-8") as output:
                json.dump(contract_mapping(plan), output, ensure_ascii=False, sort_keys=True)
            changes = [f for f in plan.files if f.before != f.after]
            result = {
                "schema_version": 1,
                "operation": "adopt-preview",
                "status": "proposal",
                "plan": str(args.output),
                "plan_digest": plan_digest(plan),
                "base": plan.base,
                "files": [
                    {"path": f.path, "action": "create" if f.before is None else "replace"}
                    for f in changes
                ],
                "binding_diff": {
                    f.path: "".join(
                        difflib.unified_diff(
                            (f.before or "").splitlines(True),
                            f.after.splitlines(True),
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
    except (OSError, ValueError, YAMLError) as error:
        return utility_failure("adopt", error)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
