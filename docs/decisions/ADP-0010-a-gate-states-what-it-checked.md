# A gate states what it checked, and a citation states what it obtained

Status: Accepted
Review date: 2026-09-02
Supersedes: None
Superseded by: None

## Context

A review of the lifecycle found several places where an operation reports a
result it did not establish.

Traceability validates that a cited decision **resolves**: the specification
names a path and the path is in the inventory. It never opens the decision. A
specification may therefore cite a decision which is still a proposal, which was
rejected, or which a later decision superseded, and the gate stays green. The
failure is not hypothetical. Delivering the decision which supersedes the
evidence-protocol decision left the superseded file still reading
`Superseded by: None`, and left a change package citing it as its governing
decision. Nothing observed either.

Shard execution has no time bound. A shard which never returns is
indistinguishable from one which is merely slow, so a gate can hang forever
while reporting nothing, and the operator has no evidence to act on.

Batch admission mutates one worktree from any number of concurrent callers. The
documented expectation is a single operator, but nothing enforces it, so two
admissions can interleave in the same batch tree and the loser's merge state is
whatever the winner left behind.

Recovering from a failed final is an ordinary re-admission: fix the member,
close it again, and admit it again. That path is real, but the public operation
list does not say so, so it has to be inferred.

Each of these is the same shape: the lifecycle asserts a property it did not
observe, or holds a property it did not state.

## Decision

A citation is checked for fulfilment, not resolution. A decision cited by a
specification must exist, must declare an accepted status, and must not be
superseded. Supersession must be recorded on both sides: when one decision
declares `Supersedes: B`, decision B must declare `Superseded by` that
decision, and delivery writes that reciprocal entry when it numbers a proposal
which supersedes something. Decision content reaches the validator through the
loading boundary, so the validator keeps validating closure without traversing
a filesystem.

Every shard executes under a declared time bound. The repository declares a
default and a shard may override it. A shard which exceeds its bound is a
distinct, reported outcome naming the shard and its bound, never an
indistinguishable failure and never an unbounded wait.

Batch mutation is exclusive. Admission and continuation hold an exclusive lock
on the batch for their duration and refuse, naming the holder, rather than
interleaving.

The recovery path is stated where the operations are stated: a failed final is
repaired by closing the member again and re-admitting it, and re-admitting an
unchanged member is a documented no-op.

## Consequences

- A green traceability result means cited decisions were obtained, not merely
  spelled correctly.
- A one-sided supersession fails instead of persisting silently.
- A hung shard is reported as a hung shard.
- Two operators cannot quietly corrupt one batch.
- The operation list stops requiring an inference to recover from a failure.
