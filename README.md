# RepoSeal

[简体中文](README.zh-CN.md)

**Keep every Agent change traceable, testable, parallel-safe, and explainable.**

RepoSeal is a language-neutral repository development foundation with a
batteries-included Python default. It turns work around coding Agents into a
repository-owned system, so delivery does not depend on chat history or one
Agent remembering what happened.

It prevents requirements disappearing, Agents asking users to rediscover the
repository, parallel work overwriting delivery branches, every member running
the full suite, and green commits that cannot explain what they delivered.

## The workflow

```text
Review → Specification → Plan → isolated worktree
       → member ready → named batch → frozen final validation
       → explicit delivery → human acceptance or reopening
```

RepoSeal records stable requirement clauses, compares declared impact with the
actual Git diff, selects named validation gates, isolates parallel work,
validates one frozen batch, and binds delivery to exact Git identities.

## Language profiles

The lifecycle does not know what language your product uses. Profiles
contribute namespaced tools, impact rules, gates, and test shards. A repository
may enable one profile or compose several:

```toml
[profiles]
enabled = ["python-default@1", "typescript-local@1"]
```

The Template enables `python-default@1`, including uv, Ruff, ty, unit and
integration test boundaries, dependency auditing, and secret detection. You
can replace it or add TypeScript, Rust, or repository-local profiles without
changing the eight lifecycle operations.

## What is enforced

- Every requirement has a valid disposition and Specification owner.
- Deferred work points to a real approved Specification.
- Plans cover every owned clause.
- Actual changes resolve to explainable profiles, gates, and shards.
- Receipts bind code, configuration, lockfiles, tools, and executed checks.
- Only explicitly named ready worktrees enter a delivery batch.
- Parallel decision proposals receive formal ADP numbers inside the batch.
- Delivery and human acceptance remain separate facts.

RepoSeal guarantees the accounting and execution boundary. Your repository
still owns its architecture, behavioral contracts, and test sufficiency.

## Start

1. Create a repository with GitHub's **Use this template** action.
2. Run `mise install`.
3. Replace the product facts in `docs/ARCHITECTURE.md`.
4. Run `just change-open <kebab-name>` and complete the generated Review.
5. Confirm the Specification, then open isolated implementation with
   `just workspace-open <branch> <base>`.

See [`docs/development-lifecycle.md`](docs/development-lifecycle.md),
[`docs/agent-team-delivery.md`](docs/agent-team-delivery.md), and
[`docs/customizing.md`](docs/customizing.md).

RepoSeal is not an Agent runtime, coding model, hosted CI service, or
Specification generator. The copied runtime is repository-owned and does not
install the RepoSeal package. Template version: `v0.2.0`.
