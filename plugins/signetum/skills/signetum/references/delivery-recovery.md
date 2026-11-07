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

On failure, inspect the structured result, retained diagnostics and exact local
and remote identities before acting. Preserve work after conflict or publication
uncertainty. Resolve an open batch merge through `batch-continue`. After a failed
final, fix a defect owned by one member in that member, run ready and admit its
new tip. Fix a defect that appears only in the combination directly in the batch
under the batch's own change record: approve it, commit, then implement and
journal the fix. Final refuses other direct implementation commits and its review
attributes each batch commit to its change. Then run ordinary final again.
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
Removals leave a retirement record with the tip, outcome and proof under the Git
common directory's `signetum/retired`.

Accepted decision filenames stay stable; final validates source without renaming
authorities or rewriting their references.

If an authorized review needs a remote branch, share a readable name. Its
publisher owns ref cleanup after delivery: verify that the exact remote tip is
reachable from the delivery branch and refuse deletion if the tip has changed.
Preserve unmerged work. Local workspace cleanup does not prune remote branches.

Batch names default to the member task names. For a combined outcome use
`batch-open --name <task-slug> --member <path> ...`. Reusing a name does not
authorize a different base or workspace role. Publication uses a readable
`Merge <task> into <target>` subject with exact source/base trailers. Ordinary
Git merges keep project hooks enabled; synthetic `commit-tree` publication does
not invoke commit hooks. Bind any required project commit-message verification
to the declared final checks rather than assume a hook validated publication.
