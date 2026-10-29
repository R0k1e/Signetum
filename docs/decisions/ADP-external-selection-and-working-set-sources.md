# Repository selection and historical working-set boundaries

Status: Accepted
Review date: 2026-10-29
Supersedes: None
Superseded by: ADP-optional-selection-and-agent-history.md

## Context

The owner reviewed the Perdura adoption proposal and authorized its Signetum-side
work first. Existing-runner bindings do not preserve a large repository's fine
test selection by themselves, and a historical constraint working set is not
necessarily an architecture decision document.

## Decision

Add one strict, source-bound selection-provider boundary. Repositories supply
selection facts and test targets; Signetum retains gate resolution, supervision,
resource budgets, diagnostic retries, failure verdicts and receipt authority.
Provider implementation and declared inputs participate in evidence identity.
Unknown coverage cannot silently reduce required validation, and final remains
complete. Existing repositories retain the current behavior without opt-in.

Add explicit committed declarations for historical working-set sources. Inventory
and preview retain exact Git provenance, source ranges, prohibitions, rationale
and reopen conditions. They never manufacture acceptance or the missing origin
of a decision. Ambiguity remains reviewable and original history remains read-only.

Engine and generated runtime share each mechanism. Perdura-specific selection
rules, paths, product imports, builds and preparation remain outside this change.
Do not nest the old complete gate, create a parallel receipt owner, introduce a
remote service or perform automatic repository adoption.

## Approval and enforcement

The owner's instruction to complete the Signetum-side changes confirms the
preceding proposal. The approved consolidated change record owns six outcomes
and their acceptance boundaries. Public behavioral tests, generated and installed
artifact checks and ordinary readiness enforce them. Stop before real integration,
delivery, publication or any Perdura modification.
