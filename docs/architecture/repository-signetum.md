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
