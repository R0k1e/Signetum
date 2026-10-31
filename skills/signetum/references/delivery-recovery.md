# Delivery and recovery

Use the repository's eight lifecycle operations: `workspace-open`, `changed`,
`ready`, `batch-open`, `batch-admit`, `batch-continue`, `final`, `batch-deliver`.
Use separate local maintenance utilities only within their authorization.
Approval to implement or passing validation does not authorize publication.

Named ready members enter a batch through admission. Before final, reconcile
retained findings with `status` and the journal tools. Final checks the
frozen source and generates the delivery review; do not write a duplicate review
file. Show the approved outcomes, standing answers, accepted decision changes,
evidence, test changes and their effect on coverage, and unfinished work before
explicitly authorized delivery. Source journals and
admitted receipts remain bound to that exact review.

On failure, inspect the structured result, retained diagnostics and exact local
and remote identities before acting. Preserve work after conflict or publication
uncertainty. Resolve an open batch merge through `batch-continue`. Otherwise fix
the member, run ready and admit its new tip, then run ordinary final again.
There is no special recovery verdict that turns a failed validation green.

Publish only through explicit `batch-deliver` with the expected base and batch
tip. A changed or missing review binding requires fresh final. Publication
recovery confirms the exact remote identity before moving the local target;
never substitute force-push, history rewriting or ad-hoc cleanup. If delivery
retains an `active_runtime` checkout, finish the operation, switch to the delivery
checkout and use its declared cleanup utility to remove that now-unused checkout.

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
