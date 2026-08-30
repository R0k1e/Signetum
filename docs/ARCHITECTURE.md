# Architecture

This branch is the independently versioned engine source of RepoSeal. It owns
the Python package, schemas, profiles, skill, tests, release automation, and
the canonical clone-ready source under `template/`. The default branch is a
deterministically rendered Template artifact; it does not contain this engine
or its governance history.

RepoSeal is the public product identity. Within this engine, the
`reposeal` distribution and `reposeal` CLI validate immutable
schema and profile identities and expose check-only repository
contracts and lifecycle operations. Rendering copies the minimal reviewed
standard-library lifecycle runtime into the Template. Existing repositories
adopt later runtime changes only as explicit local changes.

Responsibility documents:

- [RepoSeal engine](architecture/repository-reposeal.md) defines the
  package, manifest, profile, and adapter boundaries.
- [Validation and delivery](architecture/validation-and-delivery.md) defines
  check-only evidence and explicit delivery responsibilities.

Approved architecture decisions live in `docs/decisions/`. Active work is
governed by stable change packages under `changes/`.
