"""Generate portable runtime modules from their installed engine authorities."""

import argparse
import ast
import hashlib
import json
import re
import sys
from importlib.resources import files
from pathlib import Path

from signetum import __version__
from signetum.profiles.catalog import PROFILE_RESOURCE_NAMES

RUNTIME_DIRECTORY = Path(".agents/repo-dev/runtime/_signetum_runtime")
MODULES = {
    "signetum.manifest": "manifest.py",
    "signetum.validation.configuration": "configuration.py",
    "signetum.profiles.catalog": "profile_catalog.py",
    "signetum.delivery": "delivery.py",
    "signetum.operations": "operations.py",
    "signetum.operation_cli": "operation_cli.py",
    "signetum.serialization": "serialization.py",
    "signetum.git": "git.py",
    "signetum.workspaces": "workspaces.py",
    "signetum.worktrunk": "worktrunk.py",
    "signetum.findings": "findings.py",
    "signetum.waivers": "waivers.py",
    "signetum.evidence.receipts": "evidence_receipts.py",
    "signetum.impact": "impact.py",
    "signetum.validation": "validation.py",
    "signetum.validation.execution": "execution.py",
    "signetum.validation.process": "process.py",
    "signetum.validation.pytest_runner": "pytest_runner.py",
    "signetum.validation.pytest_report": "pytest_report.py",
    "signetum.validation.recovery": "recovery.py",
    "signetum.validation.resources": "resources.py",
    "signetum.validation.inheritance": "inheritance.py",
    "signetum.validation.receipt_store": "receipt_store.py",
    "signetum.validation.admission": "admission.py",
    "signetum.validation.diagnostic_protocol": "diagnostic_protocol.py",
    "signetum.validation.ratchet": "ratchet.py",
    "signetum.synchronization": "synchronization.py",
    "signetum.profiles.pip_audit": "pip_audit.py",
}


def is_runtime_cache(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def portable_source(module: str, source: str) -> bytes:
    """Change only declared internal imports; retain one maintained body."""
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            dependencies = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
                raise ValueError(f"unsupported relative dependency in {module}")
            dependencies = [node.module]
            if node.module in MODULES:
                name = Path(MODULES[node.module]).stem
                line, count = re.subn(
                    r"\bfrom\s+" + re.escape(node.module) + r"\s+import\b",
                    f"from .{name} import",
                    lines[node.lineno - 1],
                    count=1,
                )
                if count != 1:
                    raise ValueError(f"unsupported dependency import in {module}")
                lines[node.lineno - 1] = line
        else:
            continue
        for dependency in dependencies:
            if dependency.split(".")[0] not in sys.stdlib_module_names and (
                not isinstance(node, ast.ImportFrom) or dependency not in MODULES
            ):
                raise ValueError(f"unbundled dependency {dependency} in {module}")
    # Flattening package names can change their lexical order. Reorder only
    # consecutive declared top-level imports; all implementation statements stay.
    groups: list[list[ast.ImportFrom]] = []
    pending: list[ast.ImportFrom] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in MODULES:
            pending.append(node)
        elif pending:
            groups.append(pending)
            pending = []
    if pending:
        groups.append(pending)
    for group in reversed(groups):
        chunks = {node: lines[node.lineno - 1 : node.end_lineno] for node in group}
        ordered = sorted(group, key=lambda node: Path(MODULES[node.module or ""]).stem)
        for destination, original in reversed(list(zip(group, ordered, strict=True))):
            lines[destination.lineno - 1 : destination.end_lineno] = chunks[original]
    return (
        f"# Generated from {module}; edit the engine source and regenerate.\n" + "".join(lines)
    ).encode()


def runtime_files() -> dict[str, bytes]:
    result = {"__init__.py": b'"""Generated, self-contained Signetum runtime modules."""\n'}
    sources: dict[str, str] = {}
    package = files("signetum")
    for module, destination in sorted(MODULES.items()):
        parts = module.removeprefix("signetum.").split(".")
        source = package.joinpath(*parts[:-1], parts[-1] + ".py")
        if not source.is_file():
            source = package.joinpath(*parts, "__init__.py")
        source_bytes = source.read_bytes()
        sources[module] = hashlib.sha256(source_bytes).hexdigest()
        result[destination] = portable_source(module, source_bytes.decode("utf-8"))
    profile_resources = files("signetum.resources.profiles")
    for name in PROFILE_RESOURCE_NAMES:
        result["profile_resources/" + name] = (profile_resources / name).read_bytes()
    metadata = [
        "# Public content identities generated from installed engine sources.",
        "schema_version = 1",
        "engine_version = " + json.dumps(__version__),
        "",
        "[sources]",
    ]
    # Only these computed public hashes receive the scanner annotation.
    for name, digest in sorted(sources.items()):
        metadata.append(f'{json.dumps(name)} = "sha256:{digest}" # pragma: allowlist secret')
    metadata.extend(("", "[files]"))
    for name, content in sorted(result.items()):
        digest = hashlib.sha256(content).hexdigest()
        metadata.append(f'{json.dumps(name)} = "sha256:{digest}" # pragma: allowlist secret')
    result["runtime.toml"] = ("\n".join(metadata) + "\n").encode()
    return result


def runtime_problems(template: Path) -> tuple[str, ...]:
    directory = template / RUNTIME_DIRECTORY
    expected = runtime_files()
    problems = []
    for name, content in expected.items():
        path = directory / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != content:
            problems.append(f"generated runtime differs from engine source: {name}")
    if directory.exists():
        for path in directory.rglob("*"):
            if (
                not is_runtime_cache(path.relative_to(directory))
                and path.is_file()
                and path.relative_to(directory).as_posix() not in expected
            ):
                problems.append(f"unexpected generated runtime file: {path.relative_to(directory)}")
    return tuple(problems)


def generate_runtime(template: Path, *, check: bool = False) -> None:
    if check:
        if problems := runtime_problems(template):
            raise ValueError("; ".join(problems))
        return
    directory = template / RUNTIME_DIRECTORY
    expected = runtime_files()
    parent = template
    for part in RUNTIME_DIRECTORY.parts:
        parent = parent / part
        if parent.is_symlink():
            raise ValueError("generated runtime parent is a symlink")
    if directory.exists():
        for path in directory.rglob("*"):
            if path.is_symlink() or (
                path.is_file()
                and not is_runtime_cache(path.relative_to(directory))
                and path.relative_to(directory).as_posix() not in expected
            ):
                raise ValueError(f"unmanaged generated runtime path: {path}")
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    generate_runtime(arguments.template, check=arguments.check)


if __name__ == "__main__":
    main()
