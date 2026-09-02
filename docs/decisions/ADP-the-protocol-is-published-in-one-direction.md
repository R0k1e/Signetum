# The evidence protocol is published in one direction

Status: Proposed
Review date: 2026-09-02
Supersedes: ADP-0007-unified-validation-evidence.md
Superseded by: None

## Context

ADP-0007 established Evidence v3 and, alongside it, asserted a mutual
convergence with a named downstream repository, including the acceptance
criterion that RepoSeal, its Template runtime, and that downstream adapter
"pass common protocol vectors and identify the same schema digest".

That criterion passed while being unverifiable. RepoSeal ships no test which
observes a separate repository, and no separate repository consumes anything
RepoSeal publishes; each side vendored its own copy of the schema. Both sides
were green while their copies had already diverged in shape and digest. A
criterion nothing can evaluate is worse than an absent one: it reports a
guarantee that is not held.

Naming a downstream repository inside RepoSeal is the deeper error. RepoSeal is
a Template and a protocol. A consumer's identity is not a RepoSeal fact, cannot
be tested from here, and turns a published contract into a bilateral
arrangement which neither side can enforce.

## Decision

Evidence v3 stands exactly as ADP-0007 defined it. Its required sections,
extension rules, and the separation between Core, profiles, and adapters are
unchanged and are not reopened.

The protocol is published in one direction. RepoSeal defines it, ships its
schema and its conformance vectors as release artifacts, and states the
canonical schema digest. A consumer pins a RepoSeal release and demonstrates
conformance in its own repository, against those artifacts. RepoSeal makes no
claim about any consumer, names none, and carries no test which depends on one
existing.

Conformance is therefore a downstream obligation with an upstream artifact to
discharge it against, rather than a shared aspiration recorded in two places.

## Consequences

- The unverifiable cross-repository acceptance criterion is withdrawn.
- A consumer which vendors the schema can detect divergence, because the
  published vectors and digest are what it checks its copy against.
- RepoSeal's tests stop depending on facts outside this repository.
- Divergence becomes a failing vector in the consumer, instead of two green
  repositories which no longer agree.
