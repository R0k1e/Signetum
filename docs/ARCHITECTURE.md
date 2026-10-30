# Architecture

Signetum is a standard Skill for reliable agentic development and delivery.
`skills/signetum` is the public entry for both project initialization and existing
repository adoption. `main` owns the product source, runtime/setup package,
schemas, Skill, tests and documentation. Existing consumers update explicitly.

The agent obtains a fixed-version setup tool, prepares reviewed local bindings,
and then calls the project's own portable runtime. Application tools, architecture
and delivery policy remain project-owned. `template/` is internal scaffolding and
portable-runtime evidence, not a second public product or default-branch artifact.

Responsibility documents:

- [Implementation and distribution](architecture/repository-signetum.md) owns
  package, Skill, setup, source and generation boundaries.
- [Validation and delivery](architecture/validation-and-delivery.md) owns checks,
  source-bound evidence and explicit delivery.

Current authorities describe actual behavior and owners. Reconcile affected pages
in the implementing change; leave unaffected pages alone. New reasoning belongs
once in the owning change and significant append history. Standalone decisions
are conditional cross-change authorities; accepted historical sources are retained.
