# Architecture

This repository is the independently versioned source of RepoSeal, a standalone
GitHub Template for governed, Agent-native development. GitHub copies it once when a
new repository is created; the created repository then owns its product facts,
lifecycle state, package, schemas, profiles, and policy without an update or
synchronization relationship to this repository.

RepoSeal is the public product identity. Within this Template, the
`development_foundation` distribution and `foundation` CLI validate immutable
schema and profile identities and expose check-only repository
contracts. It is an internal product authority and release artifact, not a
cross-repository upgrade channel.

Responsibility documents:

- [Repository foundation](architecture/repository-foundation.md) defines the
  package, manifest, profile, and adapter boundaries.
- [Validation and delivery](architecture/validation-and-delivery.md) defines
  check-only evidence and explicit delivery responsibilities.

Approved architecture decisions live in `docs/decisions/`. Active work is
governed by stable change packages under `changes/`.
