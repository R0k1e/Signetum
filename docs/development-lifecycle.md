# Development lifecycle

Every user request starts in `changes/<change>/review.yaml`. Each independently
verifiable clause has a stable ID and one disposition: covered by a confirmed
specification, explicitly out of scope with a reason, or deferred to another
active specification. A completed change cannot contain an unresolved deferral.

The specification defines observable behavior and acceptance boundaries. The
plan maps every covered clause to implementation and behavioral validation.
Implementation begins only after human confirmation of the specification.

Development uses a plan-owned worktree. `ready` closes a member; `batch-open`
and `batch-admit` assemble only named members; `final` validates the frozen
batch once; `batch-deliver` explicitly lands that exact validated source.
`changed` is a diagnostic and `batch-continue` is conflict recovery.
