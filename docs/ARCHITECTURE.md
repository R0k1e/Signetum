# Architecture

Signetum is a plugin for reliable agentic development and delivery in Claude
Code and Codex. `plugins/signetum` carries the standard Skill
`plugins/signetum/skills/signetum`, the public entry for both project
initialization and existing repository adoption, and a command guard. Other
agent tools install that same Skill folder as a plain Skill, without the guard.
`main` owns the product source, runtime/setup package, schemas, plugin, tests and
documentation. Existing consumers update explicitly: plugins through their host
plugin managers, plain Skills in place.

The installed Skill owns one execution engine and a separately locked local
environment outside the plugin. Consumer repositories declare commands and
delivery policy in `signetum.toml` and enable the plugin in their project host
settings; their application dependencies, instructions and architecture remain
their own. Adoption does not copy the engine or impose an entry file.

Responsibility documents:

- [Implementation and distribution](architecture/repository-signetum.md) owns
  package, plugin, Skill, guard, setup, source and generation boundaries.
- [Validation and delivery](architecture/validation-and-delivery.md) owns checks,
  source-bound evidence and explicit delivery.

Current authorities describe actual behavior and owners. Reconcile affected pages
in the implementing change; leave unaffected pages alone. New reasoning belongs
once in the owning change and significant append history. Standalone decisions
are conditional cross-change authorities; accepted historical sources are retained.
