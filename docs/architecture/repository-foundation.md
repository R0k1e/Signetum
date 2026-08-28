# Repository foundation responsibilities

`development_foundation` owns generic parsing, immutable package resources,
profile composition, evidence protocols, and the check-only `foundation` CLI.
It contains no downstream application path, branch, selector, or delivery
policy.

The repository specialization manifest owns local paths and selects exact
profile identities. Profiles declare dependencies and authorities; composition
rejects unsupported identities, missing dependencies, and duplicate authority
ownership. Repository adapters implement evidence protocols, so generic
mechanisms pass typed values without inferring repository facts.
