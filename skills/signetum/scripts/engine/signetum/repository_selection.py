"""One source-bound selection boundary; execution and evidence stay generic."""

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from subprocess import TimeoutExpired  # nosec B404 -- exception only; execution uses the supervisor

from signetum.evidence.receipts import ArtifactIdentity, ToolIdentity, ValidationSelection
from signetum.git import git_output
from signetum.impact import select_paths
from signetum.manifest import RepositoryManifest
from signetum.operations import AdmissionError, InfrastructureError
from signetum.profiles import builtin_catalog
from signetum.selection_contracts import (
    SelectionProvider,
    SelectionResponse,
    repository_file,
)
from signetum.selection_request import SelectionInput, SelectionRequest
from signetum.serialization import contract_mapping, dataclass_from_mapping, load_json
from signetum.source_authority import (
    committed_blob,
    require_ancestor,
    require_committed_bindings,
    source_path,
)
from signetum.validation.configuration import configured_validation
from signetum.validation.execution import ValidationInfrastructureError
from signetum.validation.process import run_command
from signetum.validation.repository import RepositoryValidationAdapter


class SelectionError(AdmissionError):
    """Repository selection did not establish a safe execution plan."""


@dataclass(frozen=True)
class SelectionResolution:
    manifest: RepositoryManifest
    selection: ValidationSelection


def _digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _source_inputs(
    repository: Path, provider: SelectionProvider, source: str
) -> tuple[SelectionInput, ...]:
    result = []
    for relative in sorted({provider.entrypoint, *provider.inputs}):
        blob = committed_blob(repository, source, relative)
        if blob is None or source_path(repository, relative).read_bytes() != blob[1].encode():
            raise SelectionError("selection inputs must be exact committed regular files")
        result.append(
            SelectionInput(
                artifact=ArtifactIdentity.from_bytes(relative, blob[1].encode()), blob=blob[0]
            )
        )
    return tuple(result)


def _under(path: str, roots: tuple[str, ...]) -> bool:
    value = PurePosixPath(path)
    return any(value.is_relative_to(PurePosixPath(root)) for root in roots)


def select_repository(
    repository: Path,
    manifest: RepositoryManifest,
    files: tuple[str, ...],
    *,
    base: str,
    source: str,
) -> SelectionResolution:
    """Resolve an opt-in producer once against exact committed contribution inputs."""
    provider = manifest.impact.provider
    if provider is None:
        # Full execution is the default; impact rules only participate after opt-in.
        selection = replace(
            select_paths(files, ()),
            gates=("member",),
            shards=tuple(
                dict.fromkeys(
                    (
                        *next(g.shards for g in manifest.validation.gates if g.name == "member"),
                        *manifest.validation.member_required,
                    )
                )
            ),
            unexplained=(),
            requires_final=True,
            reasons=("no selection provider: run full declared member checks",),
        )
        return SelectionResolution(manifest, selection)
    try:
        return _select(repository, manifest, files, base=base, source=source)
    except (SelectionError, InfrastructureError):
        raise
    except (OSError, ValueError, TypeError) as error:
        raise SelectionError(f"selection provider refused: {error}") from error


def _select(
    repository: Path,
    manifest: RepositoryManifest,
    files: tuple[str, ...],
    *,
    base: str,
    source: str,
) -> SelectionResolution:
    provider = manifest.impact.provider
    if provider is None:
        raise SelectionError("selection provider is not declared")
    if git_output(repository, "rev-parse", "HEAD") != source:
        raise SelectionError("selection requires the current exact committed source")
    require_ancestor(repository, base, source)
    require_committed_bindings(repository, source)
    if git_output(repository, "status", "--porcelain"):
        raise SelectionError("selection requires a clean committed worktree")
    files = tuple(sorted(set(files)))
    for path in files:
        repository_file(path)
    baseline = select_paths(files, manifest.impact.rules)
    artifacts = _source_inputs(repository, provider, source)
    graph, inputs = configured_validation(manifest, catalog=builtin_catalog())
    final_names = set(graph.execution_order("final"))
    declarations = {shard.name: shard for shard in graph.shards}
    bindings = {binding.shard: binding for binding in provider.targets}
    for name, binding in bindings.items():
        shard = declarations.get(name)
        if shard is None or shard.evidence != "tree" or name not in final_names:
            raise SelectionError("target binding requires a declared final-covered tree shard")
        if binding.argument_index > len(shard.command) or shard.ratchet_command:
            raise SelectionError("target binding must replace a declared non-ratchet command tail")
    adapter = RepositoryValidationAdapter(repository)
    try:
        tools = {tool.name: adapter.identify_tool(tool) for tool in inputs.tools}
    except ValidationInfrastructureError as error:
        raise InfrastructureError(f"selection tool identity unavailable: {error}") from error
    request = SelectionRequest(
        protocol=provider.protocol,
        source=source,
        tree=git_output(repository, "rev-parse", f"{source}^{{tree}}"),
        base=git_output(repository, "rev-parse", "--verify", f"{base}^{{commit}}"),
        files=files,
        graph=graph,
        profiles=inputs.profiles,
        inputs=artifacts,
        tools=tuple(sorted(ToolIdentity(name, identity) for name, identity in tools.items())),
    )
    payload = contract_mapping(request)
    payload.pop("request_digest")
    expected = _digest(payload)
    request = replace(request, request_digest=expected)
    command = tuple(provider.entrypoint if arg == "{selector}" else arg for arg in provider.command)
    try:
        completed = run_command(
            repository,
            command,
            timeout_seconds=provider.timeout_seconds,
            input_text=json.dumps(contract_mapping(request), ensure_ascii=False),
        )
    except (OSError, TimeoutExpired) as error:
        raise InfrastructureError(f"selection provider unavailable: {error}") from error
    if completed.returncode:
        raise InfrastructureError(
            f"selection provider did not complete: {completed.stderr.strip()}"
        )
    response = dataclass_from_mapping(
        SelectionResponse, load_json(completed.stdout), use_defaults=True
    )
    if response.request_digest != expected:
        raise SelectionError("selection response does not bind the current request")
    coverage = {item.path: item for item in response.coverage}
    if len(coverage) != len(response.coverage) or set(coverage) != set(files):
        raise SelectionError("selection must account for every exact requested path once")
    selected = list(baseline.shards)
    for covered in response.coverage:
        if (
            covered.status == "covered"
            and not covered.shards
            and select_paths((covered.path,), manifest.impact.rules).unexplained
        ):
            raise SelectionError("covered path needs a shard or an explicit impact rule")
        if len(set(covered.shards)) != len(covered.shards):
            raise SelectionError("selection repeats a shard identity")
        if covered.status == "unexplained" and covered.shards:
            raise SelectionError("an unexplained path cannot claim validation coverage")
        for name in covered.shards:
            if name not in declarations or name not in final_names:
                raise SelectionError("selection names an undeclared or non-final-covered shard")
            if name not in selected:
                selected.append(name)
    targets = {item.shard: item for item in response.targets}
    if len(targets) != len(response.targets):
        raise SelectionError("selection repeats target plans")
    for name, plan in targets.items():
        binding = bindings.get(name)
        if binding is None or name not in selected:
            raise SelectionError("selection targets need an explicitly selected target binding")
        seen = set()
        for test in plan.tests:
            repository_file(test.path)
            if not _under(test.path, binding.roots) or (test.path, test.argument) in seen:
                raise SelectionError("selection target escapes its roots or repeats a test")
            if (
                test.argument.startswith("-")
                or "\0" in test.argument
                or test.argument.split("::", 1)[0] != test.path
            ):
                raise SelectionError(
                    "selection test argument must bind its exact file or file node"
                )
            blob = committed_blob(repository, source, test.path)
            if blob is None or source_path(repository, test.path).read_bytes() != blob[1].encode():
                raise SelectionError("selection target must be a committed regular test source")
            seen.add((test.path, test.argument))
    modified = tuple(
        sorted(
            set(baseline.modified_tests)
            | {
                path
                for path in files
                if any(_under(path, binding.roots) for binding in bindings.values())
            }
        )
    )
    unexplained = tuple(path for path in files if coverage[path].status == "unexplained")
    if not unexplained:
        for path in modified:
            if committed_blob(repository, source, path) is None:
                continue  # Deleted tests still invalidate inheritance, but cannot be executed.
            proven = any(
                declarations[name].evidence == "tree"
                and (
                    name not in targets
                    or (
                        name in bindings
                        and _under(path, bindings[name].roots)
                        and path
                        in {test.path for test in targets[name].tests if test.argument == test.path}
                    )
                )
                for name in coverage[path].shards
            )
            if not proven:
                raise SelectionError("selection omitted a modified test from its execution targets")
    shards = tuple(
        replace(
            shard,
            command=(
                *shard.command[: bindings[shard.name].argument_index],
                *(test.argument for test in targets[shard.name].tests),
            ),
        )
        if not unexplained and shard.name in targets
        else shard
        for shard in manifest.validation.shards
    )
    if _source_inputs(repository, provider, source) != artifacts or git_output(
        repository, "status", "--porcelain"
    ):
        raise SelectionError("selection provider changed its source inputs or working files")
    if git_output(repository, "rev-parse", "HEAD") != source:
        raise SelectionError("selection provider changed the committed source")
    try:
        current_tools = {tool.name: adapter.identify_tool(tool) for tool in inputs.tools}
    except ValidationInfrastructureError as error:
        raise InfrastructureError(f"selection tool identity unavailable: {error}") from error
    if current_tools != tools:
        raise SelectionError("selection provider changed its observed tool identities")
    chosen = replace(
        baseline,
        rules=(*baseline.rules, provider.protocol),
        shards=tuple(selected),
        modified_tests=modified,
        unexplained=unexplained,
        requires_final=bool(unexplained)
        or any(
            rule.requires_final for rule in manifest.impact.rules if rule.name in baseline.rules
        ),
        reasons=(
            *baseline.reasons,
            *(f"{item.path}: {item.reason}" for item in response.coverage),
            f"selection request {expected}",
            f"selection response {_digest(contract_mapping(response))}",
        ),
    )
    return SelectionResolution(
        replace(manifest, validation=replace(manifest.validation, shards=shards)), chosen
    )
