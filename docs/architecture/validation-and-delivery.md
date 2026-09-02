# Validation and delivery responsibilities

Ordinary validation is read-only and observes one exact commit. Evidence binds
Signetum, schema, profile, commit, and check identities. A successful member
check is not batch integration, delivery, or human acceptance.

The member and final gate build the source distribution and wheel before the
repository check graph. Integration tests therefore consume release inputs
created from the exact tree under validation, never a `dist/` directory left by
an earlier command in one worktree. The same gate also invokes the locked Ruff
check and format contracts, Bandit scan, and dependency audit used by CI; the
older isolated pre-commit tool version is feedback rather than the sole static
authority.

Every shard declares an evidence class. A `tree` shard is a pure function of
the observed tree and the bound tool identities, so a successful identity stays
successful. A `world` shard also reads mutable state outside the tree, such as
a vulnerability advisory database, so it can begin failing without any
repository change. The member gate accepts only `tree` shards, and member
narrowing defers a `world` shard reached through an impact rule to the final
gate rather than letting state the member does not own block its closure. A
`world` result records the instant it observed the world and is never a
reusable admission credential.

A failing `world` shard runs its declared findings command and reports through
the tool-neutral Signetum findings document; Signetum never parses a tool's
native output. Each reported finding is matched against the waivers tracked
under `changes/<change-id>/waivers/`. The shard is `waived` only when every
reported finding is covered by a waiver that has not expired. An uncovered
finding, an expired waiver, a missing findings command, an unparsable document,
and a failure that reports nothing all fail the gate. Evidence records `waived`
separately from `passed` together with the covering waiver and finding
identities, so a delivery states which known unrepaired findings it carries and
under whose authority.

Active Plans remain on isolated member branches. Explicit batch assembly brings
the Plan and implementation together, frozen validation observes that exact
batch, and explicit delivery retains both as durable provenance.

A workspace owns its base. `workspace-open` records the resolved base under the
machine-local state root at `signetum/workspaces/<branch>.json`, and it is
written once. `changed` and `ready` take no base argument; they read that
record, and a workspace without one fails as a precondition rather than having
a base derived for it. A batch is a workspace which declares its members, so it
carries the same record and its base is read the same way. The
`Signetum-Batch-Base` trailer stays in the provenance commit as durable
attestation, and delivery refuses a batch whose record and trailer disagree; no
operation recovers a base by searching commit prose.

A member never follows the delivery branch. Batching exists so members work
from a frozen base and integrate once, so a base which does not move is the
property that keeps parallel members independent, not a limitation.

Admission requires an evidence property rather than an evidence artifact:
durable evidence binding the member's exact tree and proving at least the shard
commands its own selection requires. Evidence is matched by observed tree and by
shard command digest, never by commit identity, receipt gate, or shard name, so
an amended trailer, an equivalent rebase, a renamed shard, and a completed final
gate all satisfy admission when the proven work is the same. When selection
reports `requires_final`, the final gate is the authority for that member and
admission records a deferred closure naming the justifying rules.

Delivery
requires the remote target to equal the approved base, derives members and Plan
trailers from the batch's admitted merge commits, fast-forwards the target,
pushes without force, and confirms the exact remote identity. Only then does it
remove the clean batch worktree and clean member worktrees still at their
admitted commits; a dirty or advanced member is retained and reported. CI may
check these contracts but does not fix, merge, publish, or delete branches.

Human control brackets implementation. Before work begins, the approved Review
and Specifications project one concise approval view containing observable
outcomes, acceptance evidence, and the execution autonomy boundary. During
work, delivery-relevant discoveries are appended through the Signetum-owned
deviation API to the repository Git common directory at
`signetum/changes/<change-id>/deviations.jsonl`; linked members and the batch
therefore share one local execution authority without committing it to the
product tree.

Before final validation, the Agent reconciles every retained discovery into
the applicable Specification, accepted clarifying or superseding Decision,
architecture authority, behavior test, explicit follow-up Change, justified
rejection, or justified no-authority-change result. `final` remains check-only:
it refuses an unresolved ledger and places approval plus reconciliation data in
the exact final receipt. The Agent projects that data as a delivery review
before explicit delivery. The review is not another tracked authority.
