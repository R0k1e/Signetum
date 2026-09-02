# Contributing

Contributions use the same governed lifecycle as product work. Before proposing
a change, read `AGENTS.md`, `docs/ARCHITECTURE.md`, and
`.agents/repo-dev/repo.yaml`. Search current production and test authorities,
then record new work under `changes/<change-id>/` as a Review, approved
Specification, and exhaustive Plan.

Use `uv` for Python commands and a Plan-owned worktree. Test observable
contracts, run targeted validation during development, and close a committed
member with `just ready`.

A ready member is not permission to deliver. Batch assembly, final validation,
remote delivery, acceptance, publication, and cleanup remain explicit maintainer
actions. See [Agent Team batch delivery](docs/workflows/agent-team-delivery.md).

Never commit credentials, local paths, caches, validation receipts, or editor state.
