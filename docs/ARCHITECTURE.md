# Architecture

This repository publishes a versioned development foundation, not a generated
application template. The foundation distribution validates immutable schema
and profile identities; consuming repositories retain ownership of all product
facts and lifecycle state.

Responsibility documents:

- [Repository foundation](architecture/repository-foundation.md) defines the
  package, manifest, profile, and adapter boundaries.
- [Validation and delivery](architecture/validation-and-delivery.md) defines
  check-only evidence and explicit delivery responsibilities.

Approved architecture decisions live in `docs/decisions/`. Active work is
governed by stable change packages under `changes/`.
