# Architecture

Signetum is a standard Agent Skill for reliable agentic development and delivery.
`skills/signetum` is the public entry for both project initialization and existing
repository adoption, and the only distributed unit: copying or unpacking that
folder into any agent tool's skills directory is a complete install. It carries an
optional command guard that an explicit `install` command registers as a
PreToolUse hook in Claude Code or Codex configuration. `main` owns the product
source, runtime/setup package, schemas, tests and documentation. Existing
consumers update explicitly: `update` replaces the Skill folder in place from the
newest published release.

The installed Skill owns one execution engine and a separately locked local
environment outside the Skill folder. Consumer repositories declare commands and
delivery policy in `signetum.toml`; their application dependencies, host
settings, instructions and architecture remain their own. Adoption does not copy
the engine or impose an entry file.

Responsibility documents:

- [Implementation and distribution](architecture/repository-signetum.md) owns
  package, Skill, guard, install, setup, source and generation boundaries.
- [Validation and delivery](architecture/validation-and-delivery.md) owns checks,
  source-bound evidence and explicit delivery.

Current authorities describe actual behavior and owners. Reconcile affected pages
in the implementing change; leave unaffected pages alone. New reasoning belongs
once in the owning change and significant append history. Standalone decisions
are conditional cross-change authorities; accepted historical sources are retained.
