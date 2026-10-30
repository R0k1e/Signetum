# A declared authority runs in a gate

Status: Accepted
Review date: 2026-09-02
Supersedes: None
Superseded by: None

## Context

The repository declares a traceability authority and ships it as a public
command. Nothing runs it. It is absent from the member gate, absent from the
final gate, and absent from continuous integration, so it is feedback a person
may choose to consult rather than a contract anything must satisfy.

The consequences are observable rather than hypothetical. The one Review in
this repository which records acceptance has never named the delivery identity
its own rule requires, and no run ever said so. The identity rename superseded
a decision and left a delivered specification citing the superseded one; that
also went unreported, and was found only because a later change happened to run
the command by hand.

The checks the authority performs are exactly the ones the lifecycle exists to
make true: that a covered clause has one owning Specification, that a Plan
covers the clauses its Specification owns, that a cited decision was obtained,
and that a claim of acceptance names what was delivered. Leaving them
unexecuted keeps the paperwork and discards the guarantee.

## Decision

The traceability authority runs in both gates as an ordinary shard. It accepts
no path scope and reports no comparable finding set, so by the member gate's
own admission rule it would belong to the final gate alone; but it is
whole-corpus by nature and cheap, and a member which breaks the requirement
chain should learn so before a batch forms. It therefore runs in both, judging
the whole corpus in each.

A Review recording acceptance names the commit which delivered it. The one
existing record is completed from the delivery its own history shows.

## Consequences

- A broken requirement chain fails a gate instead of waiting to be noticed.
- A superseded decision cannot keep a delivered specification pointing at it.
- The authority the repository declares and the behaviour it enforces stop
  disagreeing.
- Every future Review claiming acceptance must name a delivery, which is the
  rule that was always written and never held.
