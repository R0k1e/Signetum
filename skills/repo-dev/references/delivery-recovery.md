# Delivery and recovery

Use the repository's eight lifecycle operations: `workspace-open`, `changed`,
`ready`, `batch-open`, `batch-admit`, `batch-continue`, `final`, `batch-deliver`.
Use separate local maintenance utilities only within their authorization.
Approval to implement or passing validation does not authorize publication.

Named ready members enter a batch through admission. Before final, reconcile
retained findings with `status` and the journal tools. Final checks the
frozen source and generates the delivery review; do not write a duplicate review
file. Show the approved outcomes, standing answers, accepted decision changes,
evidence and unfinished work before explicit delivery. Source journals and
admitted receipts remain bound to that exact review.

On failure, inspect the structured result, retained diagnostics and exact local
and remote identities before acting. Preserve work after conflict or publication
uncertainty. Resolve an open batch merge through `batch-continue`. Otherwise fix
the member, run ready and admit its new tip, then run ordinary final again.
There is no special recovery verdict that turns a failed validation green.

Publish only through explicit `batch-deliver` with the expected base and batch
tip. A changed or missing review binding requires fresh final. Publication
recovery confirms the exact remote identity before moving the local target;
never substitute force-push, history rewriting or ad-hoc cleanup.
