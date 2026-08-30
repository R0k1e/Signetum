# Runtime configuration and Agent routing are separate authorities

Status: Accepted
Review date: 2026-08-30
Supersedes: None
Superseded by: None

## Decision

`reposeal.yaml` owns only executable runtime identity and member/final command
arrays. `.agents/repo-dev/repo.yaml` owns repository paths, Agent policy
routing, and delivery configuration. Neither duplicates the other's fields.

`change-open` is a safe authoring utility, not a ninth lifecycle operation. It
creates one draft Review, Specification, and Plan under the active `changes/`
authority and never overwrites an existing path.
