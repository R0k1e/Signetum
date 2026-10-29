# Signetum

[简体中文](README.zh-CN.md)

**Keep every Agent change traceable, testable, parallel-safe, and explainable.**

Signetum is a language-neutral repository development foundation with a
batteries-included Python default. It turns work around coding Agents into a
repository-owned system, so delivery does not depend on chat history or one
Agent remembering what happened.

It prevents requirements disappearing, Agents asking users to rediscover the
repository, parallel work overwriting delivery branches, and green commits that cannot
explain what they delivered. Member checks are complete by default; an optional
repository selection provider can reduce repeated work.

## The workflow

```text
registered member → approved change record → implementation
       → member ready → named batch → frozen final validation
       → explicit delivery → human acceptance or reopening
```

Signetum records stable requirement clauses, compares declared impact with the
actual Git diff, selects named validation gates, isolates parallel work,
validates one frozen batch, and binds delivery to exact Git identities.

## Language profiles

The lifecycle does not parse application languages. Profiles identify reviewed
capabilities, while repository declarations select actual commands. Optional
existing-runner adapters preserve the current runner; for example:

```toml
[profiles]
enabled = ["node-existing@1"]
```

The Template enables `python-default@1`, including uv, Ruff, ty, unit and
integration test boundaries, dependency auditing, and secret detection. You
can adopt `python-existing@1`, `node-existing@1` or `rust-existing@1` with
`just protocol runner --request <request-path>`. Its proposal does not run or
install anything. Merge it with existing contract, setup and batch checks;
changing the profile list alone does not change the declared runner.

## What is enforced

- One record owns requirements, approval and exhaustive execution steps.
- Deferred work names an exact active follow-up requirement.
- Significant source journals retain findings and accepted clause decisions.
- Actual changes resolve to explainable profiles, gates, and shards.
- Receipts bind code, configuration, lockfiles, tools, and executed checks.
- Only explicitly named ready worktrees enter a delivery batch.
- Accepted clause edits preserve unaffected decisions and their rationale.
- Historical Markdown proposals retain their declared numbering rules.
- Delivery and human acceptance remain separate facts.

Signetum guarantees the accounting and execution boundary. Your repository
still owns its architecture, behavioral contracts, and test sufficiency.

## Start

1. Create a repository with GitHub's **Use this template** action.
2. Inspect `mise.toml`, then run `mise trust mise.toml`, `mise install` and `uv sync --locked`.
3. Replace the product facts in `docs/ARCHITECTURE.md`.
4. Ask your coding agent to use the repository protocol for one small change,
   show the intended behavior and acceptance before implementation, and stop at ready.
5. Review the generated proposal and the final evidence. The agent authors the
   record and journal; you do not assemble protocol requests or repeat summaries.

The [Signetum first-use guide](https://github.com/R0k1e/Signetum/blob/engine/QUICKSTART.md)
explains Skill installation. This copied repository already has its local runtime;
keep its existing commands. Explicit delivery remains a separate decision.

See [`docs/development-lifecycle.md`](docs/development-lifecycle.md),
[`docs/agent-team-delivery.md`](docs/agent-team-delivery.md), and
[`docs/customizing.md`](docs/customizing.md).

Signetum is not an Agent runtime, coding model, hosted CI service, or
Specification generator. The copied runtime is repository-owned and does not
install the Signetum package. Template revision: `v0.2.0`; it is independent
from the Signetum engine package version.
