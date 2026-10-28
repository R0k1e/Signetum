# Signetum engine responsibilities

Signetum is the public product identity. Within the engine branch,
`signetum` owns generic parsing, package resources,
profile composition, evidence protocols, and the check-only `signetum` CLI.
It contains no downstream application path, branch, selector, or delivery
policy.

The repository specialization manifest owns local paths and selects exact
profile identities. Profiles declare dependencies and authorities; composition
rejects unsupported identities, missing dependencies, and duplicate authority
ownership. Repository adapters implement evidence protocols, so generic
mechanisms pass typed values without inferring repository facts. After GitHub
creates another repository from this template, that repository owns its copy
and evolves independently; this template supplies no synchronization channel.

The engine product surface is rooted at `README.md`. The canonical public
Template is rooted at `template/` and validated by an exact inventory and
deterministic render. `QUICKSTART.md`, focused
concept and workflow guides, the complete-change teaching artifact, and public
governance files explain current contracts without becoming additional
execution authorities. Repository validation checks that those required assets
and their local Markdown references remain present.


Portable shared runtime modules are maintained in the engine and enumerated by
`signetum.runtime_generation`. Generate their template artifacts with
`uv run python -m signetum.runtime_generation template`; `--check` verifies the
installed source identity without writing. Rendering refuses missing, stale or
extra generated files and omits interpreter caches. The generated package and
its public source/output digest manifest are self-contained standard-library
artifacts. Boundary adapters call these modules rather than maintaining their
bodies again. Remaining lifecycle migration is owned by the active
[tooling alignment specification](../../changes/align-perdura-development-tooling/specs/tooling.toml); generating the initial modules does not complete it.

Workspace records and change owners are validated by standard-library immutable
values in `signetum.workspaces`, not by distribution-specific models. Workspace
JSON input is normalized once by `parse_record`; both installed and generated runtimes use
the same atomic writer and immutable identity checks. A record must match its
branch path and bind a 40- or 64-character commit identity. Batch creation writes
its role and initial member list once rather than upgrading a member record.

Waiver parsing, immutable approval values, expiry and finding coverage are
owned by `signetum.waivers` and generated into the same portable runtime.
The template only translates authority errors into its operation boundary;
it does not maintain a second parser or coverage algorithm. Waiver documents
normalize TOML arrays and ISO dates once and reject unknown fields, unsupported
versions, empty approval or reason, duplicate findings and invalid expiry.

Impact selection consumes normalized read-only rule inputs rather than the
distribution's manifest parser. `signetum.impact` owns matching, ordered unions,
test-path detection, explanation and changed-path identity for both frontends.
Each configuration adapter supplies normalized fields; the template does not
maintain its own selection algorithm. The evidence values and verifier in
`signetum.evidence.receipts` are also portable standard-library artifacts, with
unchanged serialized identities. Their availability does not complete the
remaining template gate and admission migration owned by ALIGN-009.

The validation graph and generic execution engine are generated from
`signetum.validation` and `signetum.validation.execution`, including package
module sources. The template adapter supplies Git identities, declared files,
tool probes and command effects. Shared execution expands dependencies, skips
checks whose dependencies failed, continues independent checks, covers world
findings, re-observes inputs and creates the evidence document. The template
stores that document rather than reconstructing an alternate receipt shape.
Graph identity includes every declared shard field, including inheritance and
ratchet policy. Resource allocation, test recovery, inheritance qualification
and admission consumption still belong to the remaining ALIGN-009 migration.

Command supervision is owned by `signetum.validation.process` in both runtimes.
It starts its own source file with isolated Python and site-packages disabled,
so a supervisor never requires the installed engine or loads the caller's
package. A caller-held pipe controls each independent command process group;
timeouts or caller termination kill the group, including nested owners through
their own leases. The template's Mise adapter preserves environment isolation
and forwards shard deadlines; tool probes and findings have separate 60-second
limits. Shard timeout reports a failed check with its declared bound; tool and
findings timeouts report explicit observation diagnostics. Unifying the legacy
template's public operation error envelope remains part of ALIGN-009.
