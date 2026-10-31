# Architecture

Signetum is a standard Skill for reliable agentic development and delivery.
`skills/signetum` is the public entry for both project initialization and existing
repository adoption. `main` owns the product source, runtime/setup package,
schemas, Skill, tests and documentation. Existing consumers update explicitly.

The installed Skill owns one execution engine and a separately locked local
environment. Consumer repositories declare commands and delivery policy in
`signetum.toml`; their application dependencies, instructions and architecture
remain their own. Adoption does not copy the engine or impose an entry file.

Responsibility documents:

- [Implementation and distribution](architecture/repository-signetum.md) owns
  package, Skill, setup, source and generation boundaries.
- [Validation and delivery](architecture/validation-and-delivery.md) owns checks,
  source-bound evidence and explicit delivery.

Current authorities describe actual behavior and owners. Reconcile affected pages
in the implementing change; leave unaffected pages alone. New reasoning belongs
once in the owning change and significant append history. Standalone decisions
are conditional cross-change authorities; accepted historical sources are retained.
