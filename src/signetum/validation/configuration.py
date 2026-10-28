"""One manifest-to-validation projection shared by all repository adapters."""

from collections.abc import Mapping

from signetum.evidence.receipts import ValidationSelection
from signetum.manifest import ManifestError, RepositoryManifest
from signetum.profiles.catalog import ProfileDeclaration, resolve_profiles
from signetum.validation import (
    GateDeclaration,
    GraphContribution,
    ValidationGraph,
    resolve_validation_graph,
)
from signetum.validation.execution import ValidationExecutionError, ValidationInputs


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
    try:
        inputs = ValidationInputs(
            "signetum.toml",
            tuple(sorted(profile.identity for profile in resolved)),
            tuple(sorted(manifest.repository.lockfiles)),
            manifest.validation.tools,
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

    for shard in selection.shards:
        admit(shard)
    for gate in selection.gates:
        for shard in gate_shards.get(gate, ()):
            admit(shard)
    if selection.unexplained and member_closure:
        for shard in gate_shards["member"]:
            admit(shard)
    return tuple(selected), tuple(sorted(deferred))
