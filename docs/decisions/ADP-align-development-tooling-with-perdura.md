# Align development tooling with Perdura

Status: Accepted
Review date: 2026-10-28
Supersedes: ADP-0007-unified-validation-evidence.md, ADP-0001-batch-owned-decision-numbering.md, ADP-0005-unify-runtime-configuration.md, ADP-0006-public-lifecycle-consumes-v2-authorities.md, ADP-human-review-brackets-reconciled-execution.md
Partially supersedes: ADP-0007-unified-validation-evidence.md, ADP-0001-batch-owned-decision-numbering.md, ADP-0005-unify-runtime-configuration.md, ADP-0006-public-lifecycle-consumes-v2-authorities.md, ADP-human-review-brackets-reconciled-execution.md
Superseded by: None

## Context

The independent engine was incubated from Perdura but has not absorbed its later delivery, recovery, change ownership and validation improvements. The owner approved aligning those behaviors and reducing duplicate authorities.

## Decision

Use the fixed delivered Perdura baseline as behavioral source. Generic mechanisms belong to the engine; technology mechanisms belong to profiles/adapters and repository facts to manifests. A change owns one workspace from proposal through implementation. Required lifecycle operations have explicit contracts rather than a fixed operation count. Final may number accepted proposals before freezing the exact validated tip. Delivery confirms the remote before moving its local mirror.

Preserve existing findings and expiring-waiver support. Do not replace Perdura's product tooling, rename product identities, publish, or deliver as part of this authorization. The owner confirmed this decision by instructing implementation of the preceding executable plan on 2026-10-28.

## Alternatives

Copying Perdura wholesale imports application authorities. Keeping eight operations forces unsupported recovery. Maintaining engine and template independently repeats fixes. All are rejected in favor of shared generic contracts and generated artifacts.

## Enforcement

The tooling specification and real Git/CLI lifecycle scenarios own acceptance; generated template conformance protects distribution.


## Supersession boundary

Only the admission clauses of ADP-0007 are superseded: tree-only matching,
commit-independent reuse and admission without member evidence when final is
required. Other evidence, findings and waiver contracts remain in force.
Exact-tip readiness follows the owner-approved Perdura baseline.

The numbering clause of ADP-0001 is superseded only for timing: final owns
numbering, admission and continuation never number, and numbering never grants
acceptance. The base and frozen-tree guarantees remain in force.

The fixed eight-operation boundary is replaced by the documented necessary
operations. Preparation and batch gates are executable TOML declarations;
delivery branch identity is the existing repository-policy YAML responsibility.
Only those configuration/count clauses of the additional predecessors are
replaced. Human approval, reconciliation, check-only evidence and explicit
delivery boundaries remain intact.
