"""Optional Python import reach; repository families and paths remain explicit inputs."""

import ast
import fnmatch
import json
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from signetum.contract_values import FrozenContract
from signetum.git import git_output, read_blob_contents, regular_tree_files
from signetum.operation_cli import OperationParser, utility_failure
from signetum.selection_contracts import (
    PathCoverage,
    SelectionResponse,
    ShardTargets,
    TestTarget,
    repository_file,
)
from signetum.selection_request import SelectionRequest
from signetum.serialization import contract_mapping, dataclass_from_mapping, load_json


@dataclass(frozen=True, kw_only=True)
class SelectionFamily(FrozenContract):
    paths: tuple[str, ...]
    shards: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class DynamicLoader(FrozenContract):
    module: str
    imports: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class PythonSelection(FrozenContract):
    schema_version: Literal[1]
    source_roots: tuple[str, ...]
    unit_roots: tuple[str, ...]
    unit_shard: str
    families: tuple[SelectionFamily, ...] = ()
    # Explicit modules are edges for loaders that import computed module names.
    dynamic_loaders: tuple[DynamicLoader, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.source_roots or not self.unit_roots or not self.unit_shard:
            raise ValueError("selection needs source roots, unit roots and a shard")
        for root in (*self.source_roots, *self.unit_roots):
            if root != ".":
                repository_file(root)


def _under(path: str, roots: tuple[str, ...]) -> bool:
    return any(root == "." or PurePosixPath(path).is_relative_to(root) for root in roots)


def _module(path: str, root: str) -> str:
    parts = PurePosixPath(path).relative_to(root).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def dependent_units(
    files: dict[str, bytes], changed: tuple[str, ...], config: PythonSelection
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Conservative reverse reach without importing source or persisting a graph."""
    roots = (*config.source_roots, *config.unit_roots)
    sources = {p: b for p, b in files.items() if p.endswith(".py") and _under(p, roots)}
    tests = tuple(
        sorted(
            p
            for p in sources
            if _under(p, config.unit_roots)
            and (
                PurePosixPath(p).name.startswith("test_")
                or PurePosixPath(p).name.endswith("_test.py")
            )
        )
    )
    modules: dict[str, set[str]] = defaultdict(set)
    for path in {*sources, *(p for p in changed if p.endswith(".py") and _under(p, roots))}:
        for root in roots:
            if _under(path, (root,)):
                modules[_module(path, root)].add(path)
    if any(len(paths) > 1 for paths in modules.values()):
        return tests, ("ambiguous import namespace",)
    edges: dict[str, set[str]] = defaultdict(set)
    unknown = []
    loaders = {item.module: item.imports for item in config.dynamic_loaders}
    for path, blob in sources.items():
        try:
            tree = ast.parse(blob, filename=path)
        except (SyntaxError, ValueError):
            return tests, ("unparsed Python source: " + path,)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                for root in roots:
                    if not _under(path, (root,)):
                        continue
                    package = _module(path, root).split(".")
                    if not path.endswith("/__init__.py"):
                        package = package[:-1]
                    prefix = package[: len(package) - node.level + 1] if node.level else []
                    base = ".".join((*prefix, *([node.module] if node.module else [])))
                    names.add(base)
                    names.update(".".join((base, a.name)).strip(".") for a in node.names)
            elif isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                # Aliased or reflective import access is uncertainty, not proof.
                dynamic = name in {
                    "import_module",
                    "__import__",
                    "exec",
                    "eval",
                    "spec_from_file_location",
                }
                if dynamic:
                    owner_names = {name for name, paths in modules.items() if path in paths}
                    declared = [
                        target for owner in owner_names for target in loaders.get(owner, ())
                    ]
                    if declared:
                        names.update(declared)
                    elif (
                        node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                        and name in {"import_module", "__import__"}
                    ):
                        names.add(node.args[0].value)
                    else:
                        unknown.append("dynamic reach: " + path)
        # An alias for a loader can evade call-name discovery; fail closed.
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module in {"importlib", "builtins"}
                and any(
                    a.asname
                    and a.name in {"import_module", "__import__", "exec", "eval", "getattr"}
                    for a in node.names
                )
            ):
                unknown.append("aliased dynamic loader: " + path)
        for name in names:
            parts = name.split(".")
            for n in range(1, len(parts) + 1):
                edges[path].update(modules.get(".".join(parts[:n]), ()))
        if _under(path, config.unit_roots):
            edges[path].update(
                (parent / "conftest.py").as_posix()
                for parent in PurePosixPath(path).parents
                if (parent / "conftest.py").as_posix() in sources
            )
    for loader in config.dynamic_loaders:
        owner, targets = loader.module, loader.imports
        if owner not in modules or any(target not in modules for target in targets):
            raise ValueError("dynamic loader names an absent module")
        for path in modules[owner]:
            for target in targets:
                edges[path].update(modules[target])
    if any(_under(p, config.unit_roots) and p.endswith(".py") and p not in tests for p in changed):
        unknown.append("modified unit support source: run complete unit shard")
    if unknown:
        return tests, tuple(sorted(set(unknown)))
    reverse: dict[str, set[str]] = defaultdict(set)
    for importer, dependencies in edges.items():
        for dependency in dependencies:
            reverse[dependency].add(importer)
    reached = set(changed)
    queue = deque(changed)
    while queue:
        for importer in reverse.get(queue.popleft(), ()):
            if importer not in reached:
                reached.add(importer)
                queue.append(importer)
    return tuple(sorted(set(tests) & reached)), ()


def select_python(
    repository: Path, request: SelectionRequest, config: PythonSelection
) -> SelectionResponse:
    if git_output(repository, "rev-parse", "HEAD") != request.source:
        raise ValueError("selection request source differs from the repository")
    inventory = regular_tree_files(repository, request.source)
    python = {
        p: i
        for p, i in inventory.items()
        if p.endswith(".py") and _under(p, (*config.source_roots, *config.unit_roots))
    }
    blobs = read_blob_contents(repository, tuple(sorted(set(python.values()))))
    selected, fallback = dependent_units(
        {p: blobs[i] for p, i in python.items()}, request.files, config
    )
    coverage = []
    for path in request.files:
        shards = []
        for family in config.families:
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in family.paths):
                shards.extend(family.shards)
        governed = _under(path, (*config.source_roots, *config.unit_roots))
        if governed:
            shards.append(config.unit_shard)
        # Data inputs and unknown paths cannot be inferred from import reach.
        unexplained = not shards or (governed and not path.endswith(".py"))
        coverage.append(
            PathCoverage(
                path=path,
                status="unexplained" if unexplained else "covered",
                shards=() if unexplained else tuple(dict.fromkeys(shards)),
                reason="unknown input: run complete member checks"
                if unexplained
                else "; ".join(fallback) or "declared family and committed Python import reach",
            )
        )
    targets = (
        ()
        if fallback or any(c.status == "unexplained" for c in coverage) or not selected
        else (
            ShardTargets(
                shard=config.unit_shard,
                tests=tuple(TestTarget(path=p, argument=p) for p in selected),
            ),
        )
    )
    return SelectionResponse(
        protocol=request.protocol,
        request_digest=request.request_digest,
        coverage=tuple(coverage),
        targets=targets,
    )


def main(arguments: list[str] | None = None) -> int:
    parser = OperationParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    try:
        options = parser.parse_args(arguments)
        config = dataclass_from_mapping(
            PythonSelection, load_json(options.config.read_text()), use_defaults=True
        )
        request = dataclass_from_mapping(SelectionRequest, load_json(sys.stdin.read()))
        relative = options.config.resolve().relative_to(options.repository.resolve()).as_posix()
        if relative not in {item.artifact.path for item in request.inputs}:
            raise ValueError("selection configuration must be a declared provider input")
        result = select_python(options.repository, request, config)
        print(json.dumps(contract_mapping(result), sort_keys=True))
        return 0
    except (ValueError, OSError) as error:
        return utility_failure("select-python", error)
