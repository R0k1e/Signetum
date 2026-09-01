# ADP: human review brackets reconciled execution

Status: Accepted
Review date: 2026-09-01
Supersedes: None
Superseded by: None

## Context

RepoSeal closes approved Review clauses through Specifications, Plans,
validation evidence, batch provenance, and explicit delivery. Those authorities
do not retain facts discovered while implementation is running. A discovery
can therefore remain only in an Agent conversation: the implementation may
silently narrow the approved behavior, expand a Decision, or leave two accepted
Decisions in conflict while structural and test gates remain green.

Interrupting the human for every discovery is not viable for asynchronous and
multi-worktree execution. Allowing each Agent to choose a Todo list, prose file,
or chat context is not deterministic. Tracking another execution document in
the product tree would create member merge conflicts and leak transient state
into repositories created from the Template.

## Decision

**RepoSeal has two default human control points: an approval view before
implementation and a delivery review after final validation. Between them, all
delivery-relevant execution deviations are retained in one per-change ledger
and reconciled into durable authorities before final validation.**

The approval view projects the approved Specification and human direction into
observable outcomes, included scope, explicit non-goals, acceptance evidence,
and the Agent autonomy boundary. It is not a tracked source artifact.

The sole intermediate authority is logically addressed as:

```text
.git/reposeal/changes/<change-id>/deviations.jsonl
```

RepoSeal resolves this path through Git's common directory, so linked
worktrees share one logical ledger even though a linked worktree's `.git` is a
file. A repository-owned internal API validates records and serializes
concurrent writes. Agents do not edit JSON Lines directly. This support API is
not a ninth public lifecycle operation and has no Just alias.

Safe implementation clarifications and supporting changes are recorded and may
continue. A scope reduction, explicit non-goal change, incompatible accepted
Decision, destructive action, or irreversible product choice is recorded and
only the affected work is frozen. Independent execution continues without
requiring the human to remain online.

Before `final`, the Agent gives every retained deviation a terminal disposition
and updates the applicable durable authority. A behavior clarification updates
the active Specification. A conflict with an accepted Decision requires an
approved clarifying or superseding Decision with an explicit relationship. An
architecture fact updates the current architecture authority. Behavioral risk
is protected by an observable test. A deferral points to an explicit follow-up
change and remains visible as unfinished work. A rejected or no-authority-change
record carries its reason.

`final` remains check-only on one frozen batch. It verifies that all bound
deviations are terminal, cited authorities exist, Decision relationships are
valid, and no decision-required behavior was implemented without approval. Its
versioned JSON result exposes delivery-review inputs without mutating the tree.

The delivery review is presented before explicit `batch-deliver`. It compares
the approved commitment with delivered behavior and evidence, then separately
states deviations, Specification and Decision updates, extra work, and
unfinished work. It is a generated human view, not a tracked delivery file.

The engine owns the generic models, storage, projections, tests, and canonical
Template source. Deterministic rendering copies only the minimal runtime and
instructions needed by a clone-ready repository. Engine change history and
local ledgers are never rendered.

## Rejected alternatives

- **Ask immediately for every scope discovery.** This serializes independent
  execution and assumes continuous human availability.
- **Let Agents choose where to record discoveries.** Later lifecycle operations
  cannot deterministically find or reconcile those records.
- **Track one deviations Markdown file in each Change.** Concurrent members
  would edit the same source artifact and transient state would survive in the
  Template.
- **Let `final` repair source authorities.** A validator cannot mutate the
  frozen tree whose evidence it certifies.
- **Add public approval or deviation commands.** These are supporting
  projections and state recording, not new lifecycle state transitions.

## Consequences

- Humans normally inspect two concise messages instead of every Plan, Decision,
  or intermediate discovery.
- Important discoveries survive Agent context loss and worktree cleanup.
- Decision contradictions cannot be closed by a delivery message alone.
- RepoSeal gains local Git-common-dir state with explicit retention and cleanup
  rules.
- The public lifecycle remains exactly eight operations.

## Enforcement

- Engine behavior tests prove strict records, common-dir resolution, concurrent
  writes, member provenance, and terminal reconciliation.
- Template integration tests prove clone-ready repositories receive the same
  interaction and reconciliation behavior without engine history or state.
- Final validation refuses pending deviations, missing authority targets,
  dangling deferrals, and unresolved accepted-Decision conflicts.
- Structured output can render both an explicit no-deviations result and a
  complete delivery review.

## Approval

Human-approved on 2026-09-01. The user directed implementation in RepoSeal and
PyLM, with process completion preceding any further gap alignment.
