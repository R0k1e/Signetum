# Language-neutral Core with composable profiles

Status: Accepted
Review date: 2026-08-30
Supersedes: None
Superseded by: None

## Decision

RepoSeal Core owns language-neutral change accounting, impact resolution,
validation graphs, evidence, workspaces, batches, decisions, and delivery. A
profile is immutable declarative configuration that contributes namespaced
tools, impacts, gates, and shards. Repositories may enable zero, one, or many
profiles; composition is a union and ambiguous ownership fails closed.

The public Template enables `python-default`. Python tooling is not a Core
dependency, and another repository may replace Python or compose additional
language profiles without changing the eight public lifecycle operations.
`reposeal.toml` is the sole active configuration authority.

## Consequences

- Core contains no language switch or inferred project layout.
- Python receives a maintained default while other ecosystems can use the same
  protocol through repository declarations or later maintained profiles.
- Profile identities and the resolved validation graph become receipt inputs.
- The v0.2 configuration break is explicit and has no fallback parser.
