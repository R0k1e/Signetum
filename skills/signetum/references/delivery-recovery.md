# Delivery and recovery

Use the repository's seven lifecycle operations: `workspace-open`, `ready`,
`batch-open`, `batch-admit`, `batch-continue`, `final`, `batch-deliver`.
Use separate local maintenance utilities only within their authorization.
Approval to implement or passing validation does not authorize publication.

Named ready members enter a batch through admission. Admit a stacked member after
its parent, in the same `batch-admit` with the parent named first or in a later
one. Admission refuses a child whose parent's latest admission in the batch is not
the exact parent tip the child holds; synchronize the child or readmit the parent.
The final review lists each member with its own changes and its parent. Admission and
`batch-continue` run only the declared batch gate over the commits added since
its last pass; it may run no integration checks. Final stays complete, so a
failure that appears only when members combine surfaces at final. Before final, reconcile
retained findings with `status` and the journal tools. Final checks the
frozen source and generates the delivery review; do not write a duplicate review
file. Show the approved outcomes, standing answers, accepted decision changes,
evidence, test changes and their effect on coverage, and unfinished work before
explicitly authorized delivery. Source journals and
admitted receipts remain bound to that exact review.

When another batch delivers first, run `maintenance workspace-sync` in the open
batch. It merges the new delivery tip, advances the recorded batch base, keeps
every admitted member and runs the batch gate over the merged commits; then run
final again. A conflict stays open for `batch-continue`. Do not discard and
reopen the batch. If admission or synchronization refuses a decision clause ID
claimed by two changes, give one change a distinct ID, commit, run ready, retry.
When the engine no longer loads a delivered `signetum.toml`, migrate it in one
member and run ready there; `workspace-open` opens that member with preparation
`unavailable` and the cause. `status`, `batch-open`, `batch-admit` and
synchronization read only the locations of the older batch manifest, so that
member is admitted and the batch gate validates the merged manifest; `status`
reports the cause. A member that keeps the old manifest is refused.

When `batch-open` or `batch-admit` stops at a conflict, the members named after it
stay pending; the result and `status` list them, and `batch-continue` admits them
after committing the resolution.

A remembered failing node that the change deleted or renamed is released when its
shard passes without it; the receipt lists it. Other first failures stay owed.
A failed result lists `first_attempt_failures`, including those that passed only on
retry, and `failed_shards`: every shard that did not pass, with its exit code and
reported failed checks; the workspace's failure record lists the same.

On failure, inspect the structured result, retained diagnostics and exact local
and remote identities before acting. Fix every failed shard and check it lists in
one round before validating again. Preserve work after conflict or publication
uncertainty. Resolve an open batch merge through `batch-continue`. After a failed
final, fix a defect owned by one member in that member, run ready and admit its
new tip. Fix a defect that appears only in the combination directly in the batch
under the authorization recorded by `batch-open --actor <owner> --source <approval>`.
Final lists each combination repair with its commit, subject, diffstat and
authorization. No draft change record or journal entry is required. A schema-1
batch keeps its legacy rule: commit its batch-owned approval before the fix.
The hook and final judge each commit against its own parent, so a later
re-approval never invalidates an earlier authorized fix. Then run final again.
There is no special recovery verdict that turns a failed validation green.

Publish only through explicit
`batch-deliver <source-worktree> <target-worktree> <expected-base> <expected-batch-tip>`.
`source` and `target` are existing worktree directories. A branch name is not a
path. `expected-base` and `expected-batch-tip` are full commits. A changed or
missing review binding requires fresh final. Publication
recovery confirms the exact remote identity before moving the local target;
never substitute force-push, history rewriting or ad-hoc cleanup. If delivery
retains an `active_runtime` checkout, finish the operation, switch to the delivery
checkout and use its declared cleanup utility to remove that now-unused checkout.

Every workspace ends in exactly one proven outcome. Delivered: its tip is in the
delivery branch. Contained: it is clean and its content already reached the
delivery branch another way, because each commit outside it is patch-equivalent
to a delivery commit with no merge resolution of its own, or each path it changed
already has its content there. After publication `batch-deliver` sweeps every
registered workspace, removing those that prove either, and lists the rest with
the reason they stay; `maintenance cleanup --all-delivered` runs the same sweep.
Uncommitted work, an open Git operation, a fresh base or any uncontained content
always stays. `status` lists each open workspace with the outcome it proves.
Abandoned: only for work the owner decides to drop, run
`maintenance workspace-abandon <worktree> <confirmed-tip> --actor <owner> --source <confirmation> --reason <why>`
with the owner's actual confirmation of that exact full commit; never infer it.
An Agent may run it itself: `--actor` names the owner and `--source` cites where
the owner confirmed that tip, such as the conversation. It acts on the named
workspace's repository from any directory.
`maintenance leftovers` lists checkouts created outside Signetum and branches
without a checkout that the delivery branch lacks, each with its command; remove
such a branch with `maintenance branch-abandon <branch> <confirmed-tip> ...` under
the same confirmation, never raw `git branch -D`.
Removals leave a retirement record with the tip, outcome and proof under the Git
common directory's `signetum/retired`.

Accepted decision filenames stay stable; final validates source without renaming
authorities or rewriting their references.

If an authorized review needs a remote branch, share a readable name. Its
publisher owns ref cleanup after delivery: verify that the exact remote tip is
reachable from the delivery branch and refuse deletion if the tip has changed.
Preserve unmerged work. Local workspace cleanup does not prune remote branches.

Batch names default to the member task names. For a combined outcome use
`batch-open --actor <owner> --source <approval> --name <task-slug> --member <path> ...`. Reusing a name does not
authorize a different base or workspace role. Publication uses a readable
`Merge <task> into <target>` subject with exact source/base trailers. Ordinary
Git merges keep project hooks enabled; synthetic `commit-tree` publication does
not invoke commit hooks. Bind any required project commit-message verification
to the declared final checks rather than assume a hook validated publication.
