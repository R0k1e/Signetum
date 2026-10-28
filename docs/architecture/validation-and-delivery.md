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

A change package owns one isolated implementation branch from proposal through
approval and implementation. The shared Git state binds its owner at the first
discovery or readiness check and refuses a second implementation branch. A
member is ready only with approved behavior and required decisions plus its own
implementation commit after approval. A package-only member remains plan stage.
Readiness and final validation require member and batch workspace roles respectively.

Actual committed paths identify each batch's first-delivered changes and their
Plans; a trailer cannot omit or invent delivery scope. Final reviews first-delivered
packages and lists historical Plan edits separately. Delivered Review and
Specification edits are refused except for exact decision-numbering substitutions.
A later intent requires its own change rather than rewriting accepted history.

A workspace owns its base. `workspace-open` records the resolved base under the
machine-local state root at `signetum/workspaces/<branch>.json`, and it is
written once. `changed` and `ready` take no base argument; they read that
record, and a workspace without one fails as a precondition rather than having
a base derived for it. A batch is a workspace which declares its members, so it
carries the same record and its base is read the same way. The
`Signetum-Batch-Base` trailer stays in the provenance commit as durable
attestation, and delivery refuses a batch whose record and trailer disagree; no
operation recovers a base by searching commit prose.

A member's recorded base never changes. workspace-sync optionally merges an
exact delivery or verified batch snapshot without preparing dependencies.
Member path selection excludes unchanged inputs imported by supported sync
merges, so siblings' packages do not become the caller's ownership. Changed
lockfiles or generated inputs are followed by explicit worktree preparation.
Readiness remains a judgement of the member's own implementation.

Admission requires successful member-safe evidence bound to the exact member
commit, tree, recorded base, configuration, graph, profiles, lockfiles and tools.
A completed final gate can supply those checks when its complete input identity
matches. World outcomes never substitute for tree evidence. A new tip requires
fresh readiness even when its tree is unchanged. Selection's requires_final
flag declares additional batch responsibility and never waives member checks.

Delivery
requires the remote target to equal the approved base, derives members and Plan
trailers from the batch's admitted merge commits, constructs an outer merge with the approved base and batch tip as parents without
moving the target, pushes that exact commit without force, and confirms the remote
identity. Only then does it fast-forward the local target and
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
rejection, or justified no-authority-change result. `final` numbers accepted proposals under the batch lock, then validates the
frozen resulting tip. It refuses unapproved proposals and an unresolved ledger and places approval plus reconciliation data in
the exact final receipt. The Agent projects that data as a delivery review
before explicit delivery. The review is not another tracked authority.

## Operation results

Lifecycle stdout is one versioned JSON result. The envelope records operation,
status and exit_code, and keeps the business outcome under outcome. Statuses
are passed (0), invalid (2), failed (3), infrastructure_error (4), and conflict
(5). Failure records cause, context, expected recovery and the retained log
path, or null when the repository log authority is unavailable. Check output
and diagnostics go to stderr. Missing tools and unavailable identity inputs
are infrastructure failures; failed checks are validation failures. An open
merge names batch-continue instead of printing a second result.

Final numbers newly accepted, unnumbered decisions once under the batch lock.
Accepted historical decisions already present at the base keep their identities.
Numbering preserves existing supersession edges and never changes approval
status. A successor uses Partially supersedes for the subset of Supersedes
edges whose unaffected clauses remain authoritative; complete replacements
continue to invalidate current authority citations.

Discoveries are written from the package-owning member branch. A resolution is
written there while the branch is registered; once it has no registered workspace,
a supported resolution may be written from another worktree. Linked worktrees
share the same ledger and change ownership registry under Git common state.

## Workspace operations

The repository owns the delivery branch in .agents/repo-dev/repo.yaml. Runtime
commands remain in signetum.toml. The prepare gate owns dependency preparation;
the batch gate owns admission's static checks. Preparation creates no readiness
receipt and leaves the committed source unchanged. Successful preparation is
reused within the same admission/continuation operation rather than running the
same command again as a static dependency.

| Operation | Observable contract |
| --- | --- |
| workspace-open branch base | Register the exact base before preparation. Retry the same branch/base after preparation failure; refuse a changed base or role. |
| workspace-sync [--batch path] | Merge a fresh delivery snapshot or an exact same-repository batch snapshot under its lock; never rewrite the member base. |
| worktree-prepare path | Run the declared prepare gate with its time bounds, without publishing validation evidence. |
| changed [--explain] | Explain affected checks and whether final is required; it never invokes final. |
| ready | Close a clean implementation member using its recorded base and exact-tip evidence. |
| batch-open --member path [...] | Reuse or create a named batch from the fresh configured delivery base and admit only named members. |
| batch-admit batch --member path [...] | Capture and merge ready tips, then prepare and run the batch gate. Failure retains the merged state for ordinary fixup/re-admission. |
| batch-continue batch | Prepare the resolved index, check paths whose staged result differs from both parents, run batch static checks, and commit only after success. |
| final | Freeze under the batch lock, number newly accepted decisions above batch/base/fresh-remote holdings, reconcile, then validate that exact tip. |
| batch-deliver source target expected-base expected-tip | Publish only the exact validated source, confirm remote identity before moving the target, and apply the shared residue rule. |
| cleanup selector [--protected-worktree path] [--discard] | Fetch the delivery branch and remove only eligible residue selected by worktree, branch, or --all-delivered. |
| batch-discard batch | Remove only a clean unpublished and undelivered batch with no open Git operation. |

Cleanup and delivery share one removal predicate: protect delivery/user-selected
worktrees, keep fresh base-only workspaces, refuse unmerged or advanced tips and
open Git operations, and ordinarily keep dirty state. Explicit cleanup --discard
also permits unstaged and untracked state, but never a changed index. Worktrunk
performs eligible removal in the foreground with hooks disabled; automatic
member readiness never performs cleanup.

A sync conflict remains ordinary member Git state: resolve and commit it,
prepare the resulting environment, then run ready. A batch admission conflict
instead remains open for batch-continue. Neither recovery resets or rebases work.
