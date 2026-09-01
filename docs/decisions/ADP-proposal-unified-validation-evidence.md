# Validation selection and evidence have one extensible protocol

Status: Accepted
Review date: 2026-09-01
Supersedes: None
Superseded by: None

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

## Consequences

- RepoSeal and PyLM can exchange and verify the same kind of evidence without
  sharing an execution implementation.
- Member validation becomes selective while final validation remains complete.
- A protocol break requires a new schema major rather than a compatibility
  branch.
