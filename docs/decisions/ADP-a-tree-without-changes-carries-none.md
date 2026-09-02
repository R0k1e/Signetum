# A tree which hosts no Change carries no Change identity

Status: Proposed
Review date: 2026-09-02
Supersedes: None
Superseded by: None

## Context

Admission requires every member commit to name a Plan, and the plan reference
must resolve to `changes/<change-id>/plans/<file>`. The final gate then reads
`changes/<change-id>/review.toml` out of the frozen batch tree to project its
approval view. Both steps assume the delivery target hosts change packages.

The rendered Template branch does not, and must not. It contains only the
clone-ready Template, whose `changes/` directory ships empty for the repository
that will be created from it. Promoting a new render to that branch is
therefore refused: there is no Plan path to name, and had one been named, the
final gate would look for a Review which the branch is not supposed to carry.

The previous promotion predates the current rule. Its member commit named a
bare change identity rather than a plan path, which today's admission refuses
outright. So the branch has been unpromotable since that rule tightened, and
the omission was invisible because nothing tried until now.

This is the same shape as the empty-batch case already handled: an operation
demanding an identity the situation cannot produce, rather than recognising
that the situation has none.

## Decision

A Change identity is required only where a Change can exist. A repository whose
declared specification authority matches nothing hosts no change packages, and
a delivery from it carries no Change identity to name or to reconcile.

Admission accepts a member commit without a Plan trailer when the member tree
hosts no change package, and continues to refuse one otherwise. The final gate
reconciles no Change identity for such a tree and reports the empty
reconciliation explicitly rather than failing to find a Review.

A plan reference which is present is still required to resolve to
`changes/<change-id>/plans/<file>`. This decision removes a demand that cannot
be met; it does not weaken one that can.

Correctness for such a delivery rests where it already rested: on the frozen
final gate observing the exact tree.

## Consequences

- The rendered Template branch can be promoted again.
- A repository created from the Template can deliver before it records its
  first Change. Until now it could not deliver at all, which forced the first
  act to be a governed change. That forcing function becomes documentation
  rather than a gate, and this is the cost of the decision: a fresh repository
  can now land ungoverned work into itself before its first Change exists.
- Every repository which does host change packages is unaffected.
