---
name: repo-dev
description: Govern repository discovery, requirement closure, implementation, validation, delivery, recovery, and bootstrap from repository-declared authorities. Use when changing or auditing a repository; do not use it as a substitute for the repository's own manifest or authorization.
metadata:
  version: "3.0.0"
---

# Repository development

Use this skill as a lifecycle router, not as a source of repository facts. The
repository manifest selects concrete paths, profiles, commands, branches,
evidence adapters, and public operations. If the manifest is absent,
unsupported, or pins a different skill identity, stop before mutation and
report the mismatch; installing a newer skill grants no downstream authority.

## Route before acting

Classify the request as discovery, requirement closure, planning,
implementation, validation, delivery, recovery, or bootstrap. Before planning
or mutation:

1. Read the repository safety contract and architecture entry selected by the
   manifest.
2. Load every mandatory policy group plus groups selected by intent and
   affected paths.
3. Resolve Review, Specification, Plan, decision, evidence, and legacy
   authorities from the manifest. Never supply conventional paths from memory.
4. Emit a bounded manifest of the selected groups and selection reasons.

Do not proceed when a required authority cannot be resolved. Repository-owned
instructions and authorization boundaries remain controlling.

## Requirement closure

Before planning, dispatch, or behavior changes, read
[change closure](references/change-closure.md). Preserve the chain from Review
clause through its one current approved Specification owner, exhaustive Plan
obligations, implementation evidence, delivery, and human acceptance.

A dispatch selects obligations for execution; it cannot reduce approved scope.
Never call a whole Plan complete from a partial dispatch or an agent report.
Deferral requires an approved transfer of ownership before the current work can
continue toward closure.

For new behavior, changed accepted behavior, durable architecture/process/
security choices, planning, or supersession, read
[specification, plan, and decision gates](references/spec-plan-decisions.md).

## Work and evidence

Use only the workspace and environment authorities named by the manifest.
Preserve unrelated work and keep external mutation within the user's explicit
authorization. For implementation, member readiness, or final validation,
read [worktree and validation](references/worktree-validation.md).

Report these derived states separately:

- **ready**: member evidence passes for its exact source identity;
- **integrated**: the member is included in a named integration identity;
- **delivered**: the validated integration reached the declared target;
- **accepted**: a human accepted the delivered Review clauses.

The state of a parent is the least-complete state of its clauses. None of these
states implies a later one.

For integration, delivery, acceptance, rejection, or failed-workflow recovery,
read [delivery and recovery](references/delivery-recovery.md). Delivery,
publication, remote mutation, and cleanup need their own repository-declared
authority; validation never implies permission for them.

## Bootstrap boundary

When creating a repository specialization, keep generic lifecycle decisions in
this versioned skill and repository facts in the downstream manifest and its
focused policies. Select technology profiles only from repository evidence.
Do not create duplicate runners, aliases, selectors, or delivery mechanics.
