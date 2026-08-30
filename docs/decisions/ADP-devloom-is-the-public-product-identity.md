# DevLoom is the public product identity

Status: Accepted
Review date: 2026-08-30
Supersedes: None
Superseded by: ADP-reposeal-is-the-public-product-identity.md

## Context

“Development Foundation” accurately described a category but did not provide a
memorable product identity. “Python CI/CD Template” described an earlier and
much narrower repository. The current Template governs the complete path from
recorded requirements through isolated parallel development, frozen validation,
explicit delivery, and human acceptance.

## Decision

The public product name is **DevLoom**. Its primary positioning is **“Weave
requirements into verified releases.”** The weaving metaphor represents atomic
requirement threads becoming one inspectable delivery through Specifications,
Plans, isolated worktrees, tests, batches, and delivery evidence.

The Python distribution `development-foundation`, import package
`development_foundation`, and `foundation` CLI remain internal machine protocol
identifiers for this change. They are not alternate product names. Renaming
those public machine contracts would require a separate Specification covering
commands, package metadata, schemas, fixtures, release artifacts, and migration.

DevLoom remains a standalone GitHub Template. A repository created from it owns
its copied workflow and does not receive automatic DevLoom upgrades.

## Consequences

- Public product surfaces use one memorable identity and outcome statement.
- Search-oriented pages can answer the category and use-case questions directly.
- Internal identifiers remain stable and have an explicit responsibility boundary.
- A later machine-identifier rename cannot be hidden inside branding work.
