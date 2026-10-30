# Generated from signetum.validation.configuration; edit the engine source and regenerate.
"""One manifest-to-validation projection shared by all repository adapters."""

from collections.abc import Mapping
from dataclasses import replace

from .evidence_receipts import ValidationSelection
from .execution import ValidationExecutionError, ValidationInputs
from .manifest import ManifestError, RepositoryManifest
from .profile_catalog import ProfileDeclaration, resolve_profiles
from .validation import (
    GateDeclaration,
    GraphContribution,
    ValidationGraph,
    resolve_validation_graph,
)


def configured_validation(
    manifest: RepositoryManifest,
    *,
    catalog: Mapping[str, ProfileDeclaration],
    member_shards: tuple[str, ...] | None = None,
    base: str | None = None,
    selection: ValidationSelection | None = None,
) -> tuple[ValidationGraph, ValidationInputs]:
    resolved = resolve_profiles(
        manifest.profiles.enabled, replacements=manifest.profiles.replacements, catalog=catalog
    )
    gates = manifest.validation.gates
    if member_shards is not None:
        retained = tuple(item for item in gates if item.name != "member")
        gates = (*retained, GateDeclaration("member", member_shards))
    graph = resolve_validation_graph(
        (GraphContribution("repository", manifest.validation.shards, gates),)
    )
    tools = manifest.validation.tools
    files = tuple(sorted(manifest.repository.lockfiles))
    if provider := manifest.impact.provider:
        by_name = {tool.name: tool for tool in tools}
        if len(by_name) != len(tools) or len(set(files)) != len(files):
            raise ManifestError("selection requires unique validation tools and artifact inputs")
        files = tuple(sorted({*files, provider.entrypoint, *provider.inputs}))
        for tool in provider.tools:
            if tool.name in by_name and by_name[tool.name] != tool:
                raise ManifestError("selection and validation declare conflicting tool identities")
            by_name[tool.name] = tool
        tools = tuple(by_name.values())
    try:
        inputs = ValidationInputs(
            "signetum.toml",
            tuple(sorted(profile.identity for profile in resolved)),
            files,
            tools,
            base=base,
            selection=selection,
            schema_digest=manifest.signetum.evidence_schema_digest,
            recovery_threshold=manifest.validation.recovery_threshold,
            recovery_window=manifest.validation.recovery_window,
        )
    except ValidationExecutionError as error:
        raise ManifestError(str(error)) from error
    return graph, inputs


def member_shards(
    manifest: RepositoryManifest, selection: ValidationSelection, *, member_closure: bool = True
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the member shards to execute and the world shards left to final.

    Member closure stays a function of the observed tree, so a world shard
    reached through an impact rule or a composed gate is deferred rather than
    allowed to make an unrelated member unclosable.
    """

    gate_shards = {gate.name: gate.shards for gate in manifest.validation.gates}
    world = {item.name for item in manifest.validation.shards if item.evidence == "world"}
    selected: list[str] = list(manifest.validation.member_required) if member_closure else []
    deferred: list[str] = []

    def admit(name: str) -> None:
        if name in world:
            if name not in deferred:
                deferred.append(name)
            return
        if name not in selected:
            selected.append(name)

    if manifest.impact.provider is None:
        # Do not permit callers or old impact projections to narrow the default.
        for shard in (*gate_shards["member"], *manifest.validation.member_required):
            admit(shard)
        return tuple(selected), tuple(sorted(deferred))

    for shard in selection.shards:
        admit(shard)
    for gate in selection.gates:
        for shard in gate_shards.get(gate, ()):
            admit(shard)
    if selection.unexplained and (member_closure or manifest.impact.provider is not None):
        for shard in gate_shards["member"]:
            admit(shard)
    return tuple(selected), tuple(sorted(deferred))


def with_deferred_world(
    selection: ValidationSelection, deferred: tuple[str, ...]
) -> ValidationSelection:
    return (
        replace(
            selection,
            reasons=selection.reasons
            + tuple(f"world shard {name} deferred to final" for name in deferred),
        )
        if deferred
        else selection
    )
