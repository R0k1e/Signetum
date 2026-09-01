# Public lifecycle consumes the version-two authorities

Status: Accepted
Review date: 2026-09-01
Supersedes: None
Superseded by: None

## Context

RepoSeal already defines manifest impact rules, composable validation graphs,
and exact schema-version-two evidence. The public lifecycle bypasses those
authorities with a fixed command list, a boolean changed-file selector, and a
second schema-version-one receipt. The copied Template runtime also implements
the boundary independently, so ordinary code reuse cannot prevent drift.

## Decision

The eight public operations consume `reposeal.toml` as their sole tracked
configuration. `changed` projects the actual Git diff through its impact rules
without executing validation. `ready` and `final` execute the selected named
boundary and persist exact schema-version-two evidence.

Machine-local state has one untracked authority rooted at the Git common
directory: `reposeal/validation`, `reposeal/delivery`, and `reposeal/changes`.
Tracked configuration cannot redirect these operational records.

The engine runtime and the standard-library Template runtime remain separate
deployable implementations. Shared black-box contract vectors define their
common observable behavior and both test suites consume those vectors.

RepoSeal engine releases and rendered Template revisions remain independent
semantic identities. Documentation must label them explicitly; equality is
neither required nor implied.

## Consequences

- A green public lifecycle receipt proves the already-declared v2 contract.
- Selective diagnostics no longer claim every changed tree requires final.
- Worktrees share local evidence without committing it or configuring a path.
- Runtime duplication remains intentional but semantic drift becomes testable.
