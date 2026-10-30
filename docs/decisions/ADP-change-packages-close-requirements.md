# Change packages close requirements through human acceptance

Status: Accepted
Review date: 2026-08-28
Supersedes: None
Superseded by: None

## Context

A branch receipt can prove that a commit passed its declared tests while still
failing to prove that every user requirement entered the declared scope. A
requirement that exists only in conversation can be omitted from a
Specification, narrowed in a dispatch brief, or left as an untyped prose gap.
A green member gate cannot detect that missing upstream obligation.

Review, Specification, Plan, validation evidence, delivery, and human
acceptance answer different questions. Treating any one as the whole lifecycle
causes partial implementation to be reported as completion.

## Decision

Every new governed change lives at one stable path:

```text
changes/<change-id>/
  review.yaml
  specs/<spec-id>.yaml
  plans/<plan-id>.md
```

The path never moves between draft, active, delivered, or archived directories.

A Review records source requirements as stable atomic clauses, approved
exclusions, delivery-linked acceptance, rejection, and reopening. It does not
define technical behavior.

A Specification owns observable behavior. Every active Review clause has
exactly one current approved Specification owner. A Specification defines
inputs, outputs, positive and negative contracts, invariants, boundaries,
deferrals, and supersession. It does not manually claim implementation,
integration, delivery, or acceptance.

A Plan owns one implementation path from an approved base. Every clause owned
by its Specification maps to explicit obligations and acceptance evidence. A
Plan and a dispatch brief cannot narrow an approved Specification. Deferral
first transfers the clause to another approved Specification.

Member-ready, batch-integrated, delivered, and human-accepted are distinct
states derived from repository evidence and Review acceptance. The state of a
parent item is the least-complete state of its clauses.

An active Plan stays outside the delivery branch. The same explicit delivery
that lands the implementation also lands its Specification and Plan as durable
provenance. Acceptance or reopening refers to that delivery.

Legacy roots may be declared read-only. Legacy documents remain valid historical
authorities and are not migrated; new files under those roots are rejected.

## Rejected alternatives

### Put review item numbers only in prose

Rejected because prose cannot prove uniqueness, ownership, or closure.

### Make each original review item map to exactly one Specification

Rejected because a user item can contain several independently testable
contracts. Atomic clauses, not broad item numbers, receive one owner.

### Store all completion states in YAML

Rejected because a hand-written state can disagree with the exact commit,
receipt, batch, or delivery.

### Keep completed Plans only on temporary branches

Rejected because worktree cleanup would remove the durable explanation and
break later requirement and acceptance audits.

### Migrate every historical Specification and Plan

Rejected because it creates large mechanical churn without improving the
closure of new work.

### Add another public lifecycle command

Rejected because traceability is composed into existing repository validation
and exposed through a read-only query, not a second runner.

## Consequences

- A new change needs one Review plus one or more approved Specifications and
  Plans.
- Scope reduction becomes a human-visible contract change.
- Status reports become projections rather than manually maintained tables.
- Rejected or changed accepted behavior creates a reopen or superseding
  contract rather than rewriting history.
- Repositories must bind their evidence and delivery adapters.
- Static validation gains an additional check but the success path retains one
  final gate.

## Enforcement

- Schema validation enforces IDs, states, and references.
- Traceability validation enforces one owner, exhaustive Plan coverage,
  deferral, supersession, exclusion approval, acceptance, and reopening.
- Member validation rejects new legacy-root documents and incomplete governed
  Plans affected by the member.
- Frozen final validation recomputes traceability on the exact batch.
- Delivery consumes final evidence and never reinterprets requirements.

## Workflow cost

| Measure | Before | After |
| --- | ---: | ---: |
| Success-path commands | Repository-specific | Unchanged public operation count |
| Success-path full gates | 1 | 1 |
| New persistent authorities | 0 requirement-side authorities | 1 change-package authority |
