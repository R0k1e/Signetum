# Validation and delivery responsibilities

Ordinary validation is read-only and observes one exact commit. Evidence binds
RepoSeal, schema, profile, commit, and check identities. A successful member
check is not batch integration, delivery, or human acceptance.

The member and final gate build the source distribution and wheel before the
repository check graph. Integration tests therefore consume release inputs
created from the exact tree under validation, never a `dist/` directory left by
an earlier command in one worktree. The same gate also invokes the locked Ruff
check and format contracts, Bandit scan, and dependency audit used by CI; the
older isolated pre-commit tool version is feedback rather than the sole static
authority.

Active Plans remain on isolated member branches. Explicit batch assembly brings
the Plan and implementation together, frozen validation observes that exact
batch, and explicit delivery retains both as durable provenance. Delivery
requires the remote target to equal the approved base, derives members and Plan
trailers from the batch's admitted merge commits, fast-forwards the target,
pushes without force, and confirms the exact remote identity. Only then does it
remove the clean batch worktree and clean member worktrees still at their
admitted commits; a dirty or advanced member is retained and reported. CI may
check these contracts but does not fix, merge, publish, or delete branches.

Human control brackets implementation. Before work begins, the approved Review
and Specifications project one concise approval view containing observable
outcomes, acceptance evidence, and the execution autonomy boundary. During
work, delivery-relevant discoveries are appended through the RepoSeal-owned
deviation API to the repository Git common directory at
`reposeal/changes/<change-id>/deviations.jsonl`; linked members and the batch
therefore share one local execution authority without committing it to the
product tree.

Before final validation, the Agent reconciles every retained discovery into
the applicable Specification, accepted clarifying or superseding Decision,
architecture authority, behavior test, explicit follow-up Change, justified
rejection, or justified no-authority-change result. `final` remains check-only:
it refuses an unresolved ledger and places approval plus reconciliation data in
the exact final receipt. The Agent projects that data as a delivery review
before explicit delivery. The review is not another tracked authority.
