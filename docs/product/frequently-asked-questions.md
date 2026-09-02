# Frequently asked questions

## What is Signetum?

Signetum is an Agent-development repository Template that connects recorded
requirements, approved behavior, repository-aware Plans, isolated parallel
work, behavior tests, frozen batch validation, explicit delivery, and human
acceptance in one inspectable lifecycle.

## Is Signetum another CI template?

No. CI is one validation consumer. Signetum also governs requirement capture,
behavior specifications, implementation Plans, repository discovery, isolated
Agent work, batch composition, exact validation evidence, delivery provenance,
acceptance, and recovery.

## Is it just an `AGENTS.md` file?

No. `AGENTS.md` is the always-loaded safety kernel. The repository manifest
routes tasks to current architecture and focused policies; typed change packages
and validation enforce relations that prose instructions cannot prove.

## Does it guarantee that no requirement is ever missed?

It guarantees structural coverage for requirements recorded as Review clauses.
It cannot guarantee that a human statement was interpreted perfectly, which is
why Specification approval and delivered acceptance remain human decisions.

## How does it reduce test cost without reducing quality?

Members use targeted or changed validation for feedback. Ready evidence binds
to each exact member commit. Explicitly named members are combined, then the
complete gate runs once on the frozen batch that will be delivered.

## Can several coding Agents work at the same time?

Yes. Each member has an isolated Plan-owned worktree and branch. Members do not
mutate the delivery worktree or merge themselves. Batch admission preserves
their histories and handles conflicts at the combined boundary.

## What does a delivery contain?

Its structured result identifies the approved base, member branches and
commits, integrated commits, Plan paths, validated batch tip, final receipt,
delivery commit, remote commit, and controlled cleanup.

## Does a repository receive later Template updates?

No. GitHub Template creation is a one-time copy. The new repository owns and
customizes its lifecycle independently. A useful later idea can be implemented
manually there as an ordinary local governed change.

## Is Signetum a specification generator?

No. Signetum can coexist with a specification authoring tool, but it owns the
larger repository lifecycle: requirement ownership, implementation obligations,
isolated Agent work, validation identity, batch composition, delivery
provenance, and post-delivery acceptance. See
[Signetum and specification tools](signetum-and-specification-tools.md).

## What are the package and command called?

The distribution, Python import, and command are all named `signetum`. Version
3 intentionally removes the earlier `development_foundation` and `foundation`
identities instead of keeping compatibility aliases.

## Does `final` automatically deliver?

No. `final` is check-only. Delivery is an explicit operation with exact source,
target, base, and batch-tip identities. A delivered change is still not human
accepted until its Review records acceptance.
