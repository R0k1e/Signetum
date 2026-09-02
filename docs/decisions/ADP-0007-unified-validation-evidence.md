# Validation selection and evidence have one extensible protocol

Status: Accepted
Review date: 2026-09-02
Supersedes: None
Superseded by: ADP-0009-the-protocol-is-published-in-one-direction.md

## Decision

RepoSeal defines Evidence v3 as the common protocol for member and final
validation. Its required sections are identity, selection, execution,
completeness, and provenance. Repository-specific evidence is admitted only
under a namespaced extensions map and cannot replace a required core field.

`changed` computes and reports selection without executing it. `ready` binds
that selection to the exact source and base, executes its selected shards plus
profile-declared completeness requirements, and records the result. `final`
does not reuse member narrowing: it executes the complete graph once on the
frozen batch tip.

Core contains no language, frontend, storage, retry, or worker-allocation
branch. Profiles contribute shards, complete sets, impact rules, and external
obligation declarations. Repository adapters execute specialized obligations
and may record namespaced extensions.

The protocol identity contains the canonical schema digest. Independently
implemented runtimes claiming the protocol must pass the same black-box vectors
and emit that identity.

### Every shard declares an evidence class

A shard is `tree` or `world`. A `tree` shard is a pure function of the observed
tree and the bound tool identities: the same identity always yields the same
verdict. A `world` shard also consumes mutable state outside the tree, such as
a vulnerability advisory database, so a previously successful identity may fail
later without any repository change.

The member gate accepts only `tree` shards. Declaring a `world` shard in the
member gate, in `member_required`, or reaching one through member narrowing is
a configuration error. Member closure therefore cannot be invalidated by state
the member does not own.

A `world` shard records the instant it observed the world. Evidence identity
stays reusable for `tree` shards alone; a `world` result proves only the run
that produced it.

### A failing world shard may be covered by expiring per-finding waivers

A `world` shard may declare a findings command emitting the RepoSeal findings
document. When the shard command fails, RepoSeal executes that command and
matches each reported finding against the waivers tracked under
`changes/<change-id>/waivers/`. The shard is `waived` only when every reported
finding is covered by a waiver that has not expired; any uncovered finding, any
expired waiver, an absent findings command, and an unparsable findings document
each fail the shard.

A waiver names its approver, its exact findings, and a mandatory expiry. It is
tracked repository content subject to ordinary human review. Evidence records
`waived` separately from `passed`, together with the covering waiver and
finding identities, so a delivery states which known unrepaired findings it
carries and under whose authority.

RepoSeal defines the findings document; it does not parse any tool's native
output. Profiles and adapters own that translation.

### Admission requires an evidence property, not an evidence artifact

A member is admissible when durable evidence binds its exact tree and proves at
least the shard commands its own selection requires. Evidence is matched by
observed tree and by shard command digest, never by commit identity or shard
name, so an amended trailer, an equivalent rebase, a renamed shard, and a
completed final gate all satisfy admission when the proven work is the same.

When selection reports `requires_final`, the final gate is the authority for
that member and admission accepts a recorded deferred closure naming the rules
that justified it.

## Consequences

- RepoSeal and PyLM can exchange and verify the same kind of evidence without
  sharing an execution implementation.
- Member validation becomes selective while final validation remains complete.
- A protocol break requires a new schema major rather than a compatibility
  branch.
- Mutable external state can no longer block member closure, and the delivery
  it does reach is explicit, attributable, and expiring.
- Re-running a gate to regenerate an identical artifact stops being a
  precondition for delivery.
