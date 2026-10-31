# Readable integration identities

Status: Accepted
Review date: 2026-10-31
Supersedes: None
Superseded by: None

The owner approves task names for integration branches and publication subjects.
A default name derives from the member branches; coordinators may supply a short
explicit name. Git ref validation and existing immutable workspace registration
refuse unsafe names or reuse at a different base. Names aid review, while exact
base, member, source and receipt identities remain the delivery authority.

Publication messages keep exact batch and base identities in trailers. Retry
recognition continues to use parents and tree identity, never the subject.
Project commit conventions remain project-owned. Synthetic commit-tree publication
does not run Git commit hooks; instructions must disclose that boundary rather
than imply a hook ran. This change adds no forced hook or project policy.

Full-SHA branch names were deterministic but obscured the work in GitHub. Human
names preserve deterministic retries for one integration and let coordinators
name a combined outcome. Reopen if real conflicting integrations require a
stronger explicit naming policy; never use names as evidence identity.
