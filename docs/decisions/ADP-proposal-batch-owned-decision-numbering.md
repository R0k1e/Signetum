# Batch-owned decision numbering

Status: Accepted
Review date: 2026-08-30
Supersedes: None
Superseded by: None

## Decision

Member worktrees create decisions as `ADP-proposal-<slug>.md` and never claim a
formal number. After explicit admission, the batch orders its new proposals
deterministically, allocates `ADP-0001-<slug>.md` identities from the exact
approved delivery base, rewrites governed references, and records the rewrite
in a dedicated commit before frozen final validation.

Formal identities must be unique, but historical gaps are valid. A changed
delivery base invalidates numbering and final evidence.

## Consequences

- Parallel members cannot independently collide on the next number.
- Final validation observes only formal decision identities.
- Delivery can prove which base authorized the allocated number range.

