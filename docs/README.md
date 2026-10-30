# Documentation

Start with [First use](../QUICKSTART.md). The agent handles setup syntax and uses
the repository's existing application tools.

- [Working with Signetum](guide.md): changes, decisions, tests, parallel delivery,
  profiles and limitations.
- [Existing runners](guides/existing-runners.md) and [repository bindings](guides/repository-bindings.md): explicit adoption/configuration contracts.
- [Structured selection](guides/structured-selection.md): optional source-bound test selection.
- [Architecture](ARCHITECTURE.md): maintained implementation and validation owners.
- [Contributing](../CONTRIBUTING.md), [releasing](maintainers/releasing.md) and [security](../SECURITY.md): maintenance.
- [Decision history](decisions/README.md): retained rationale; not required first-use reading.

Architecture describes owners and invariants; guides explain use and optional
configuration. `maintainers/` serves development and release of Signetum itself.
The separate `maintenance` command group handles local preparation, synchronization
and cleanup; it is not another daily lifecycle.
