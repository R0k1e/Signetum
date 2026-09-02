# Delivery and recovery

Read this reference for integration, delivery, publication, cleanup,
acceptance/rejection, or recovery from a failed lifecycle operation.

## Preserve authorization boundaries

Use only the public operations and identities declared by the repository
manifest. Assembly, admission, conflict continuation, final validation,
delivery, publication, remote mutation, and cleanup are distinct capabilities.
Do not infer authorization for a later operation from approval or success of an
earlier one.

An integrated member is not delivered. A delivered change is not accepted.
Human acceptance is recorded against the delivered Review clauses through the
repository's acceptance authority. Human rejection preserves the delivery
record and starts the declared reopen or supersession path.

## Recover from evidence

Begin recovery read-only. Record workspace status, source and target
identities, integration identity, local and remote state when applicable, and
the last valid evidence. Identify the failed invariant and its owning
repository authority before mutation.

Retain recoverable workspaces after conflicts, authentication failures,
publication failures, or remote uncertainty. Continue only through the
repository-declared recovery operation. Do not replace a refusal with history
rewriting, forced updates, unapproved direct integration, or ad-hoc cleanup.

After any synchronization or mutation, recompute the affected evidence; stale
validation cannot establish the new identity. Report the furthest proven state
for each clause and name the exact missing authority or evidence for the next
state.

## Recover by re-entering the ordinary path

A failed complete gate has no dedicated recovery operation and needs none.
Repair the member, close it again, and admit it again; a member already
integrated at its current identity is a no-op, so re-entry is safe to retry.
Integration state is mutated by one operator at a time, and an operation which
cannot hold it refuses and names the holder rather than proceeding.
