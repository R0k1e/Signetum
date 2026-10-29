"""Generate portable runtime modules from their installed engine authorities."""

import argparse
import ast
import hashlib
import json
import re
import sys
from importlib.resources import files
from itertools import pairwise
from pathlib import Path

from signetum import __version__
from signetum.profiles.catalog import PROFILE_RESOURCE_NAMES
from signetum.vendor_resources import yaml_payload

RUNTIME_DIRECTORY = Path(".agents/repo-dev/runtime/_signetum_runtime")
MODULES = {
    "signetum.profiles.existing_runner": "existing_runner.py",
    "signetum.change_open": "change_open.py",
    "signetum.protocol_cli": "protocol_cli.py",
    "signetum.traceability.records": "traceability_records.py",
    "signetum.change.paths": "change_paths.py",
    "signetum.maintenance": "maintenance.py",
    "signetum.source_authority": "source_authority.py",
    "signetum.migration": "migration.py",
    "signetum.development_log": "development_log.py",
    "signetum.development_store": "development_store.py",
    "signetum.validation.process_observation": "process_observation.py",
    "signetum.change_record": "change_record.py",
    "signetum.decision_history": "decision_history.py",
    "signetum.decision_clauses": "decision_clauses.py",
    "signetum.lifecycle": "lifecycle.py",
    "signetum.workspace_operations": "workspace_operations.py",
    "signetum.validation.repository": "repository.py",
    "signetum.profiles": "profiles.py",
    "signetum.policy": "policy.py",
    "signetum.change.member": "change_member.py",
    "signetum.lifecycle_validation": "lifecycle_validation.py",
    "signetum.provenance": "provenance.py",
    "signetum.execution_review": "execution_review.py",
    "signetum.validation.review": "validation_review.py",
    "signetum.change.authority": "change_authority.py",
    "signetum.deviations": "deviations.py",
    "signetum.contract_values": "contract_values.py",
    "signetum.change.models": "change_models.py",
    "signetum.change.scope": "change_scope.py",
    "signetum.decision_identity": "decision_identity.py",
    "signetum.status.models": "status_models.py",
    "signetum.status.projector": "status_projector.py",
    "signetum.traceability.boundary": "traceability_boundary.py",
    "signetum.traceability.loading": "traceability_loading.py",
    "signetum.traceability.validator": "traceability_validator.py",
    "signetum.traceability.cli": "traceability_cli.py",
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
    "signetum.preparation": "preparation.py",
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


EXTERNAL_IMPORTS = {"yaml": "vendor_yaml"}
IMPORTS = {**MODULES, **EXTERNAL_IMPORTS}


def is_runtime_cache(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def _module_aliases(node: ast.ImportFrom) -> bool:
    return bool(node.module) and all(
        f"{node.module}.{alias.name}" in MODULES
        and Path(MODULES[f"{node.module}.{alias.name}"]).stem == alias.name
        for alias in node.names
    )


def portable_source(module: str, source: str) -> bytes:
    """Bind declared imports/resources while retaining one maintained algorithm."""
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    imports: dict[ast.Import | ast.ImportFrom, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            dependencies = [alias.name for alias in node.names]
            if len(node.names) == 1 and node.names[0].name in MODULES and node.names[0].asname:
                if node.end_lineno != node.lineno:
                    raise ValueError(f"unsupported module alias import in {module}")
                alias = node.names[0]
                imports[node] = "."
                lines[node.lineno - 1] = (
                    f"from . import {Path(MODULES[alias.name]).stem} as {alias.asname}\n"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
                raise ValueError(f"unsupported relative dependency in {module}")
            if _module_aliases(node):
                dependencies = [f"{node.module}.{alias.name}" for alias in node.names]
                destination = "."
            else:
                dependencies = [node.module]
                destination = (
                    "." + Path(IMPORTS[node.module]).stem if node.module in IMPORTS else None
                )
            if destination is not None:
                imports[node] = destination
                line, count = re.subn(
                    r"\bfrom\s+" + re.escape(node.module) + r"\s+import\b",
                    f"from {destination} import",
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
                (not isinstance(node, ast.ImportFrom) and node not in imports)
                or dependency not in IMPORTS
            ):
                raise ValueError(f"unbundled dependency {dependency} in {module}")
    # The resource adapter differs only in its declared package namespace.
    if module == "signetum.profiles":
        bindings = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "PROFILE_RESOURCE_PACKAGE"
                for target in node.targets
            )
        ]
        if (
            len(bindings) != 1
            or not isinstance(bindings[0].value, ast.Constant)
            or bindings[0].value.value != "signetum.resources.profiles"
        ):
            raise ValueError("unsupported profile resource binding")
        lines[bindings[0].lineno - 1] = (
            'PROFILE_RESOURCE_PACKAGE = "_signetum_runtime.profile_resources"\n'
        )
    groups: list[list[ast.Import | ast.ImportFrom]] = []
    pending: list[ast.Import | ast.ImportFrom] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node in imports:
            pending.append(node)
        elif pending:
            groups.append(pending)
            pending = []
    if pending:
        groups.append(pending)
    for group in reversed(groups):
        chunks = {node: lines[node.lineno - 1 : node.end_lineno] for node in group}
        ordered = sorted(group, key=lambda node: imports[node])
        gaps = [
            line
            for previous, following in pairwise(group)
            for line in lines[previous.end_lineno : following.lineno - 1]
        ]
        if all(not line.strip() for line in gaps):
            lines[group[0].lineno - 1 : group[-1].end_lineno] = [
                line for node in ordered for line in chunks[node]
            ]
        else:
            for destination_node, original in reversed(list(zip(group, ordered, strict=True))):
                lines[destination_node.lineno - 1 : destination_node.end_lineno] = chunks[original]
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
    result.update({"vendor_yaml/" + name: content for name, content in yaml_payload().items()})
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
