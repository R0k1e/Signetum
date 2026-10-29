# Signetum engine responsibilities

Signetum is the public product identity. Within the engine branch,
`signetum` owns generic parsing, package resources,
profile composition, evidence protocols, and the check-only `signetum` CLI.
It contains no downstream application path, branch, selector, or delivery
policy.

The repository specialization manifest owns local paths and selects exact
profile identities. Profiles declare dependencies and authorities; composition
rejects unsupported identities, missing dependencies, and duplicate authority
ownership. Repository adapters implement evidence protocols, so generic
mechanisms pass typed values without inferring repository facts. After GitHub
creates another repository from this template, that repository owns its copy
and evolves independently; this template supplies no synchronization channel.

The engine product surface is rooted at `README.md`. The canonical public
Template is rooted at `template/` and validated by an exact inventory and
deterministic render. `QUICKSTART.md`, focused
concept and workflow guides, the complete-change teaching artifact, and public
governance files explain current contracts without becoming additional
execution authorities. Repository validation checks that those required assets
and their local Markdown references remain present.


Portable runtime modules have one maintained engine source, enumerated by
`signetum.runtime_generation`. Generate the template artifacts with
`uv run python -m signetum.runtime_generation template`; `--check` checks the
installed source without writing. Rendering refuses stale, missing or extra
generated files, omits interpreter caches, and binds public source/output hashes.
The generated owned modules use the standard library; adapters own repository effects.
The delivery-policy reader additionally bundles the exact locked pure-Python
PyYAML sources and license, preserving full safe YAML semantics without requiring
a separate installed dependency. Upstream bytes are stored as package data and
are not maintained as an engine parser fork. Refresh them after a reviewed lock
update with `uv run python -m signetum.vendor_resources
src/signetum/resources/vendor_yaml`, then regenerate and verify the runtime.

| Shared authority | Responsibility |
| --- | --- |
| `manifest`, `validation.configuration` | One strict TOML boundary, configuration defaults, member selection and declared-input projection; canonical validation value types. |
| `profiles.catalog`, `serialization` | Owned profile syntax, maintained catalog parsing and dependency/authority composition; portable typed JSON values. |
| `delivery` | Remote-first publication and exact interrupted-publication recovery after adapter-owned qualification. |
| `operations`, `git`, `source_authority`, `workspaces` | Operation values, isolated Git context, committed source proofs and immutable workspace/change records. |
| `worktrunk` | Supervised Mise execution, repository environment projection and registered workspace inventory parsing. |
| `preparation` | Configured preparation execution with clean or staged-state guards and unchanged source identity. |
| `operation_cli` | Shared argument refusals, result categories and retained operation diagnostics. |
| `change_record`, `decision_clauses`, `decision_history`, `development_log`, `development_store` | Consolidated approval, targeted clause edits, significant source journals and their deterministic current decision projection. |
| `contract_values`, `change.models`, `change.paths`, `traceability`, `status` | Frozen change values, native and wire constraints, complete relation checks and derived status. |
| `change.authority`, `change.scope`, `decision_identity`, `deviations` | Declared authority standing, committed change scope, explicit identity moves and the locked append-only ledger. |
| `change.member`, `lifecycle_validation`, `provenance`, `execution_review`, `validation.review` | Member qualification, actual package Plans, exact validation and final review/receipt bindings through repository effect adapters. |
| `findings`, `waivers` | Tool-neutral findings and approved, expiring coverage. |
| `impact`, `validation` | Rule selection, dependency graphs and policy-bound graph identity. |
| `evidence.receipts`, `validation.receipt_store`, `validation.admission`, `validation.inheritance` | Exact evidence values/storage, complete member qualification and conservative ancestor reuse. |
| `validation.execution`, `process`, `resources`, `recovery`, `pytest_runner`, `pytest_report` | Execution, supervised commands, native resource budgets and retained failed-node recovery. |
| `validation.diagnostic_protocol`, `validation.ratchet`, `synchronization` | Diagnostic multisets and snapshot measurements against verified synchronization sources. |

The observable contracts are maintained in
[Validation and delivery](validation-and-delivery.md), rather than repeated
here. Configuration adapters normalize inputs and supply effects; they do not
maintain alternate selection, execution or evidence verdict algorithms. The
template uses one configuration projection for validation and admission.
Configuration readers explicitly permit owned defaults; reusable receipt
readers continue to require every serialized field without coercion.
`requires_final` never substitutes for missing member checks. Native Linux/macOS
resource observations and explicit host-adapter observations consume the same
budget algorithm.

Profile resources are emitted byte-for-byte from the installed engine catalog.
Both adapters use the same parser and resolver. Evidence names resolved
dependencies and replacements rather than the unresolved enabled list; catalog
selection does not implicitly execute commands omitted by the repository.

The generated lifecycle includes the canonical workspace operations, delivery
policy, batch admission and final decision numbering. Its command-line entry
point only delegates to that lifecycle. Common real-Git workspace and admission
cases exercise both the engine and generated library; isolated template and
installed-distribution cases check the packaged boundary.
[Tooling alignment](../../changes/align-perdura-development-tooling/specs/tooling.toml)
owns the complete requirement and acceptance scope.

The record and decision-history preview commands never grant approval.
`development_store` owns mutations for consolidated records: one source journal
at `changes/<change-id>/events.jsonl` retains significant observations,
dispositions and exact accepted decision transactions. The current topic-aware
working set is derived on read, so there is no second handwritten summary or
cross-file partial update. `current` returns that working set; `status-all`
returns observation dispositions; `history` retrieves a change or event's
original rationale and approval provenance on demand.

Mutations require an active member workspace, its exact registered base and a
committed approved contract. Requests name the expected approval digest, so a
stale request cannot be reinterpreted under a revised approval. A common-Git
writer lock, expected history digest,
per-journal hash chain, protected committed prefix and atomic replacement bound
each append. An exact retry is idempotent. Reconciliation validates all changes
before writing; a failed target or decision amendment changes no source bytes.
Ordinary execution-step refinements do not invalidate unchanged behavior
approval. Completed and withdrawn records cannot authorize new writes.

An independently identified decision proposal in the contract is accepted by
that contract's exact approval. Its authority reference is
`changes/<change-id>/change.toml#decisions/<transaction-id>`; the generated
current view retains context, affected clauses and provenance without requiring
another handwritten Markdown copy. History binds the original approval commit
and blob, rather than reinterpreting old acceptance from the latest record.
Deferral requires an explicit approved requirement transfer to an active
follow-up requirement. A retraction names the exact standing resolution and
returns its observation to pending; it never withdraws the observation or
carries a replacement answer. Withdrawals apply before standing resolutions
are judged, so a semantically invalid old answer has an append-only repair.
Raw `history` remains readable in that case, and the refused status view
reports the history identity needed by the repair request.

Evidence retirement requires an exact proposal in the approved contract and
committed deletion of those targets since the registered base. It retains the
original resolution, its outcome, other evidence and the retiring contract's
provenance; it does not claim a new implementation of the old finding.
Mutation output contains the affected observations and decision identities,
rather than repeating the entire current set or source history.

Existing traceability and the common-Git deviation API remain in force until
the explicit legacy and lifecycle migration in
[RELIABLE-006 and RELIABLE-011](../../changes/reliable-agentic-protocol/specs/protocol.toml)
is integrated. The new command reports `authority_coverage = journal_only`;
its working set does not silently absorb or replace historical Markdown
decisions. Candidate preview input is never treated as an accepted journal.

`migration inventory` captures committed Review, Specification, Plan and
decision sources by exact Git blob identity. It uses the same parsers and
relationship validator as ordinary traceability. Single-clause specifications
and unique exact-text matches expose structural acceptance mappings; other
relations and unassigned acceptance entries remain explicit review issues.
Legacy bases are retained rather than guessed from the current branch, and an
old document that the current parser cannot interpret remains a named source
with a diagnostic. Inventory never repairs or rewrites accepted history.

`migration preview` requires an inventory identity, explicit source line spans,
stable clause IDs and topic context. It displays original excerpts beside the
proposed clauses. Changed authorities or uncommitted source edits refuse the
preview, while independent code-only commits preserve unchanged source bindings.
Partial supersession uses the same predicate as traceability and never revives
a fully replaced rule. Every preview remains unapproved; selecting a few lines
does not declare a legacy decision completely migrated or grant write authority.

Member qualification reads a committed consolidated `change.toml` as its sole
change authority when present. Competing Review, Specification or Plan files
refuse qualification rather than supplying fallback approval. The record must
be active, approved, identify the owning change and bind the registered workspace
base. An implementation commit must follow approval of the exact current
contract; an earlier approved contract cannot qualify a revised outcome.

For consolidated changes, delivery scope names `change.toml` as the actual
execution-plan owner. Delivered intent, contract and approval remain protected,
while execution-step refinements can preserve the same behavior approval.
Legacy package readers remain available for the historical and in-flight
packages pending the remaining traceability and review migration; qualification
of a consolidated member does not imply that this wider migration is complete.

Repository approval queries use the safe consolidated-record loader and a
version-two review projection: each requirement appears once with its stable
ID, outcome and acceptance, alongside excluded scope, explicit transfers,
autonomy and the exact recorded approval. The view does not repeat flat
outcome or acceptance summaries and never creates approval. Competing legacy
files, path identity mismatches, symlinks and stale approval bindings refuse.

Traceability discovers consolidated records under the declared change root,
checks exact active follow-up requirement ownership, and uses the same evidence
progress algorithm as historical packages. A draft remains specified; an
approved record's execution plan is the record itself. Ready, integration and
delivery require matching observations, and a completed record never implies
human acceptance. Historical version-one review projections remain unchanged
while source journals and final-review reconciliation are being integrated.
