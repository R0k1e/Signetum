# Reliable agentic development and delivery protocol

Status: approved
Specification: `changes/reliable-agentic-protocol/specs/protocol.toml`
Base: `05182737e34d0aa1ad7418837f8c0f089a409cea`

The owner authorized the preceding proposal on 2026-10-29. One package owns
this workspace through implementation. Preserve the three prior ready members
and both delivery worktrees. Do not open a delivery batch or publish.

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| IMPLEMENT-001 | RELIABLE-001 | A first validation failure remains failed even if its diagnostic retry passes; fresh normal validation after a fix may pass. Original and retry evidence remain available, and infrastructure failures retain their category. |
| IMPLEMENT-002 | RELIABLE-002 | Each change has one structured development record for intent, approved behavior, acceptance and necessary execution planning, with append-only significant development events rather than duplicate handwritten reports. |
| IMPLEMENT-003 | RELIABLE-003 | Decisions have stable clause identities, versions, scopes and source events; amendments, retractions, splits and merges name exact affected clauses and expected prior versions while retaining unaffected clauses. |
| IMPLEMENT-004 | RELIABLE-004 | A topic-organized current decision working set exposes context, effective choices, boundaries, relationships and provenance as a verified projection of accepted history, maintained through one update path. |
| IMPLEMENT-005 | RELIABLE-005 | Local log tools support recording, resolving, retracting, atomic reconciliation, retiring stranded authority references and repository-wide status without erasing history or allowing independent manual edits of projections. |
| IMPLEMENT-006 | RELIABLE-006 | Migration inventories historical records and produces reviewable clause mappings; ambiguous granularity is explicit and historical accepted records remain read-only rather than being guessed or bulk rewritten. |
| IMPLEMENT-007 | RELIABLE-007 | Significant events needed by source review are captured before committing and validating the source. Validation and delivery do not mutate that frozen source to append their own success. Ordinary output remains in local receipts and logs. |
| IMPLEMENT-008 | RELIABLE-008 | Every supported command job is checked for owned leftover processes on success, failure, timeout and cancellation; bounded cleanup reports ownership and turns a leaked successful job into failure without touching unrelated jobs. |
| IMPLEMENT-009 | RELIABLE-009 | Protocol and execution are independent of application language. Minimal repository bindings and optional Python, Node and Rust adapters use existing repository runners and preserve their authorities. |
| IMPLEMENT-010 | RELIABLE-010 | The product is one standard skill plus local commands and conditional instructions; no cross-machine synchronization, remote ledger, service platform, account system or automatic adoption is introduced. |
| IMPLEMENT-011 | RELIABLE-011 | Agent entrypoints and skill references explicitly route through the current decision working set, create one change record, retrieve rationale on demand and generate approval and delivery views without duplicate summaries. |
| IMPLEMENT-012 | RELIABLE-012 | Product material presents a reliable agentic development and delivery protocol with a minimal example, three reproducible failure demonstrations, a practice article and an existing-repository adoption example; claims distinguish measured mechanisms from unmeasured impact. |
| IMPLEMENT-013 | RELIABLE-013 | Behavioral acceptance covers four change types, partial decision amendments, concurrency and bad references, command process ownership, installed skill operations and Python, Node and Rust repositories, including negative and recovery cases. |

## Execution

1. Tighten retry verdicts and preserve both failed-attempt reports.
2. Implement and exercise the consolidated change/event and clause-decision
   model, accepted-history projection, local transactions and migration preview.
3. Add command-owned process settlement for supported Linux/macOS hosts.
4. Separate language-neutral defaults from Python/Node/Rust bindings and adapt
   traceability, authority and review consumers to the new record owner.
5. Update the skill, prompts, generated template, installed-artifact contracts
   and truthful product examples. Reuse earlier ready contributions through
   supported integration only; never silently merge their owner worktrees.
6. Audit every acceptance clause, build artifacts, run required gates and stop
   at a clean ready. No obligation becomes complete from a smaller test subset.

Use uv sync --locked, uv run and uv build. Reproduce changed verdicts through
public runners before implementation. Extend observable tests at each boundary;
use the declared gate for complete validation and inspect installed artifacts.
Record delivery-relevant discoveries through the deviation API and reconcile
all retained entries. Raw logs do not become additional tracked summaries.

## Autonomy

Safe implementation clarifications and reversible supporting work may proceed.
Freeze affected work for a changed commitment, incompatible accepted decision,
destructive action or irreversible choice. No cross-machine services, source
history rewrite, real batch integration, delivery, publication or outreach.
