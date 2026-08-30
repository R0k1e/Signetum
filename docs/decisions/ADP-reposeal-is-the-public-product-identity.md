# RepoSeal is the public product identity

Status: Accepted
Review date: 2026-08-30
Supersedes: ADP-devloom-is-the-public-product-identity.md
Superseded by: None

## Context

DevLoom provided a useful metaphor but conflicts with established developer
products and domains. The product requires a distinct identity that describes
its repository boundary and its evidence-backed delivery outcome without
binding it to Python, CI, or one coding Agent.

## Decision

The public product name is **RepoSeal** and its primary line is **“Seal every
change with evidence.”** “Repo” names the execution boundary. “Seal” represents
both the product's harbor-seal mark and the exact requirement, validation, and
delivery provenance attached to a completed change.

The public GitHub repository page is the product homepage. RepoSeal does not
require a separately hosted website for launch. Search and Agent discovery rely
on an answer-oriented README, focused documentation, repository metadata, and
formal releases.

The Python distribution `development-foundation`, import package
`development_foundation`, and `foundation` CLI remain internal machine protocol
identifiers. Their separate responsibility is explicit and is not a competing
brand.

## Consequences

- Current public surfaces use RepoSeal exclusively.
- The superseded DevLoom decision remains historical evidence.
- One canonical mark is scaled rather than independently redrawn.
- GitHub metadata and releases are part of product completeness.
