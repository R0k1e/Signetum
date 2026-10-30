# Keeping an Agent change reviewable

A useful delivery review answers four questions: what was approved, what changed,
what evidence supports it, and what remains unresolved. Reconstructing those
answers from a long chat or several handwritten summaries creates work for both
the reviewer and the next Agent.

Signetum keeps one change record for the approval boundary and an append-only
journal for significant discoveries. Routine command output stays in receipts
and logs. Approval and delivery views are generated from their source inputs.
The goal is to preserve decisions and their basis without asking the owner to
review an execution diary.

## Start from the current decisions

Before proposing implementation, the Agent reads the repository's architecture,
selected policies and current decision working set. A relevant clause points to
its history when the reason matters. A small amendment names the affected clause
and expected version; it does not override an entire decision document. The
current working set is derived, so there is one mutation path instead of a log
and a separately edited summary that can disagree.

Historical adoption is still explicit. An empty journal projection does not
mean the repository has no decisions. Relevant legacy authorities continue to
apply until reviewed mappings establish their new representation.

## Confirm the observable boundary once

For a health endpoint change, the record names the response to preserve, its
acceptance test and permitted execution autonomy. The owner reviews that compact
view. A changed behavior or scope requires the applicable new confirmation;
routine refinement of execution steps does not invent a second approval ritual.
Architecture, process and security choices retain identified accepted decisions.

## Record discoveries where they affect the answer

If implementation exposes an incompatible existing rule, record the finding
through the local tool and freeze the affected choice. Continue independent
work. Resolve it into the applicable authority, test, explicit follow-up or
justified terminal disposition. Retraction preserves the earlier answer and why
it ceased to apply. Ordinary test success does not need a journal entry.

Commit significant source events before validation. Final validation reads the
frozen source and emits receipts; it does not append its own success to that
source and invalidate the identity it just checked.

## Review evidence at its actual boundary

Readiness covers an exact member tip. A batch admits named members and final
validation covers the combined frozen source. Publication is a separate explicit
operation; a successful check grants no publication permission. Human acceptance
requires its own evidence and is never inferred from a green receipt.

The [failure demonstrations](failure-demonstrations.md) show missing ownership,
stale evidence and publication recovery with their fixture limitations. The
[existing-runner guide](../guides/existing-runners.md) shows adoption without
replacing an application's test framework. These examples demonstrate mechanisms;
they do not establish a measured reduction in review time or defects.
