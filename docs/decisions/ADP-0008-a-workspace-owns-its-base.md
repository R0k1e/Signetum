# A workspace owns its base and a batch is a workspace

Status: Accepted
Review date: 2026-09-02
Supersedes: None
Superseded by: None

## Context

`workspace-open` resolves the requested base, verifies that the created
workspace sits at exactly that commit, returns the base in its JSON result, and
persists nothing. Every later operation is re-told the base by its caller:
`changed <base>` and `ready <base>` both take it as a positional argument. The
base is therefore a claim made at validation time rather than a fact the
workspace carries.

Two consequences follow. Evidence stops being a function of the workspace,
because one tree yields different member receipts depending on which base the
caller names, and the selection those receipts record differs with it. And a
wrong base cannot be detected where it is used; the disagreement only surfaces
during admission, which derives its own answer and compares.

The protocol also holds two incompatible answers to the same question. A
member's base is a caller-supplied string held nowhere. A batch's base is a
commit trailer recovered by regular expression over commit history, with a
fallback that scans every merge commit reachable from the tip. `batch-open` is
already implemented as `workspace-open` plus a provenance commit plus
admission, so the two are one concept in the code and two mechanisms in the
model.

A member does not need to follow the delivery branch. Batching exists so that
members work from a frozen base and integration happens once, at assembly and
the final gate. A base that never moves is therefore not a limitation; it is
the property that makes parallel members independent.

## Decision

A workspace owns its base. `workspace-open` writes a workspace record under the
existing machine-local state root at `reposeal/workspaces/<branch>.json`,
alongside `reposeal/validation`. The record states the branch, the resolved
base, whether the workspace is a member or a batch, and, for a batch, the
members it declares. The base is written once and never changes.

`changed` and `ready` take no base argument. They read the workspace record.
A workspace without a record is a precondition failure, not an invitation to
derive one.

A batch is a workspace that declares members. `batch-open` writes a workspace
record of kind `batch` exactly as a member workspace does, and the batch's base
is read from that record rather than parsed out of commit prose. The public
operation count is unchanged.

`RepoSeal-Batch-Base` remains in the provenance commit as durable, auditable
history, and delivery verifies that the trailer and the record agree. It is no
longer the mechanism by which an operation discovers its own base, so the
fallback scan over every reachable merge commit is removed. One authority
answers the question; the trailer attests to the answer.

## Consequences

- One tree yields one member verdict, and the base backing it cannot be
  misreported by a caller.
- A member and a batch answer "what is your base" through one path.
- Recovering a base no longer depends on parsing commit messages.
- The eight public operations keep their names; two of them lose an argument.
- A machine-local record is lost with the clone. Delivery still verifies the
  durable trailer, so a lost record blocks work rather than corrupting a
  delivery.
