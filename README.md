# RepoSeal repository starter

[简体中文](README.zh-CN.md)

This repository is ready for agent-team development. RepoSeal keeps every
request traceable through review, specification, plan, implementation,
behavioral validation, batch assembly, and explicit delivery.

Public Template version: `v0.1.0`.

## Start

1. Replace the product facts in `docs/ARCHITECTURE.md`.
2. Run `just change-open <kebab-name>` and complete the generated Review.
3. Confirm the specification before implementation.
4. Open an isolated worktree with `just workspace-open <branch> <base>`.

The eight public lifecycle operations are documented in
[`docs/development-lifecycle.md`](docs/development-lifecycle.md). They run from
the repository-owned standard-library runtime; cloning does not install a
RepoSeal package or copy RepoSeal's engine source and maintainer history.

## What this starter guarantees

- Requirements cannot silently disappear from the review-to-spec graph.
- Agents discover the repository's own architecture and validation authority.
- Work is developed in parallel worktrees and delivered in explicit batches.
- Validation protects observable behavior and runs once on the frozen batch.
- Delivery evidence identifies exactly what was shipped.

Application code, frameworks, and deployment choices remain yours.
