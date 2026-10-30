# Signetum implementation responsibilities

Signetum is the public product identity. Within the product source,
`signetum` owns generic parsing, package resources,
profile composition, evidence protocols and the `signetum` CLI. Check and preview
operations observe; authoring, adoption, workspace and delivery operations mutate
only within their declared authority.
It contains no downstream application path, branch, selector, or delivery
policy.

The repository specialization manifest owns local paths and selects exact
profile identities. Profiles declare dependencies and authorities; composition
rejects unsupported identities, missing dependencies, and duplicate authority
ownership. Repository adapters implement evidence protocols, so generic
mechanisms pass typed values without inferring repository facts. After explicit adoption, each project owns its local runtime and evolves
independently; installation does not establish an automatic synchronization channel.

The product surface is rooted at `README.md` and the standard Signetum Skill.
Internal scaffolding under `template/` is validated by inventory and deterministic
render for runtime tests; it is not a public installation route. `QUICKSTART.md`, focused
concept and workflow guides and public governance files explain current contracts without becoming additional
execution authorities. Repository validation checks that required assets and
local Markdown references remain present. The same public-surface authority
checks structured workflow permissions, triggering-commit checkout and exact
external-action identities, without pinning teaching prose or command spelling.


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
| `operation_cli`, `workflow_status` | Shared argument refusals and diagnostics; read-only workspace, change and recorded-evidence overview. |
| `change_record`, `decision_clauses`, `decision_history`, `development_log`, `development_store` | Consolidated approval, targeted clause edits, significant source journals and their deterministic current decision projection. |
| `contract_values`, `change.models`, `change.paths`, `traceability`, `status` | Frozen change values, native and wire constraints, complete relation checks and derived status. |
| `change.scope`, `decision_identity`, `deviations` | Declared authority standing, committed change scope, explicit identity moves and read-only historical ledger evidence. |
| `change.member`, `lifecycle_validation`, `provenance`, `execution_review`, `validation.review` | Member qualification, actual package Plans, exact validation and final review/receipt bindings through repository effect adapters. |
| `findings`, `waivers` | Tool-neutral findings and approved, expiring coverage. |
| `impact`, `repository_selection`, `selection_contracts`, `selection_request`, `validation` | Explicit source-bound selection, dependency graphs and policy-bound execution identity. |
| `python_selection` | Optional committed Python import reach through the existing selection protocol; manifest rules own families. |
| `test_scheduling`, `pytest_scheduling`, `ci_partitions` | Pure weighted units and grouping, pytest adaptation, source-bound optional CI plans/results; no lifecycle receipt authority. |
| `release` | Exact delivered engine source eligibility and component identities, shared by local and hosted preflight. |
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
The validation and delivery responsibility page owns these observable contracts.

The record and decision-history preview commands never grant approval.
`development_store` owns mutations for consolidated records: one source journal
at `changes/<change-id>/events.jsonl` retains significant observations,
dispositions and exact accepted decision transactions. The current topic-aware
working set is derived on read, so there is no second handwritten summary or
cross-file partial update. `current` returns that working set; `status` derives the workspace, change,
observation and source-current recorded receipt overview without execution;
`history` retrieves a change or event's
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

Historical documents and common-Git ledgers remain readable for inspection and
source-bound delivery review. They cannot authorize new member development or
receive new protocol writes. The new command reports `authority_coverage = journal_only`;
its working set does not silently absorb or replace historical Markdown
decisions. `current` also discovers committed accepted decision sources, their
blob identities and declared supersession standing, so one entrypoint exposes
both clause history and retained authority without interpreting prose. Candidate preview input is never treated as an accepted journal.

Agents organize historical working sets using the repository's ordinary change
and decision process, preserving original sources and rationale for review.
The engine does not parse constraint tables or assign semantic meaning to their
rows. Source text and mapping previews never confer approval.

Member qualification reads a committed consolidated `change.toml` as its sole
change authority. Competing Review, Specification or Plan files
refuse qualification rather than supplying fallback approval. The record must
be active, approved, identify the owning change and bind the registered workspace
base. An implementation commit must follow approval of the exact current
contract; an earlier approved contract cannot qualify a revised outcome.

For consolidated changes, delivery scope names `change.toml` as the actual
execution-plan owner. Delivered intent, contract and approval remain protected,
while execution-step refinements can preserve the same behavior approval.
Historical package sources remain protected; they provide no fallback approval.

Repository approval queries use the safe consolidated-record loader and a
version-two review projection: each requirement appears once with its stable
ID, outcome and acceptance, alongside excluded scope, explicit transfers,
autonomy and the exact recorded approval. The view does not repeat flat
outcome or acceptance summaries and never creates approval. Competing legacy
files, path identity mismatches, symlinks and stale approval bindings refuse.

Traceability discovers consolidated records under the declared change root,
checks exact active follow-up requirement ownership and derives progress from
source-bound evidence. Historical Review/Specification/Plan files are not active
query or execution inputs. A draft remains specified; an
approved record's execution plan is the record itself. Ready, integration and
delivery require matching observations, and a completed record never implies
human acceptance. Historical version-one review projections remain readable. Consolidated journals
and final-review reconciliation use the same committed source qualification.

The standard `skills/signetum` folder contains one routing `SKILL.md`, conditional
references and a local shell launcher. The launcher delegates to the consuming
repository's adopted `.agents/repo-dev/run protocol`, or its existing `just protocol`; it does not fetch code, adopt policy or install
an application runner. The wheel carries that same folder for ordinary skill
installation. Installed-artifact tests run its commands against a disposable
consumer using the consumer's existing interpreter, including paths with spaces
and refusal of unadopted repositories.

`change_open` is the single authoring owner, shared by engine and generated
runtime. It requires a registered member, refuses the declared delivery branch
and unsafe destinations, and creates one unapproved record bound to the recorded
base. The protocol dispatcher routes authoring, concise proposal views, journal
operations and explicit test diagnostics to their existing
owners. Test diagnostics delegate to the normal repository execution adapter;
they do not own another runner or readiness store. Candidate views
expose the exact base, approval digest and retirement proposals without recording
confirmation. The retired ledger has no writing API or command. Agent instructions
use these commands, preserve relevant legacy authorities during `journal_only`
coverage, and require significant journals rather than duplicate reports.

The optional `profiles.existing_runner` adapter accepts typed, explicit Python,
Node or Rust runner requests. It uses the existing validation value types and
preserves argv, tool identities and deadlines. Its maintained profile identities
own only their opt-in runner capability; `shared-core@1` remains the dependency.
It neither detects languages from paths nor installs or executes an application.
`protocol runner` emits an unapproved configuration fragment and omits retired
retry tuning. Repository adoption retains its existing core and preparation
checks and selects any additional tools or inputs explicitly.

Native host acceptance traverses ordinary failure, fresh readiness, named
admission and final for all three languages in engine and generated frontends.
Those external host-tool scenarios are marked world and never enter engine
member inheritance; pure adapter and isolated CLI contracts remain tree tests.
The application package metadata remains unchanged, and Node/Rust scenarios
contain no Python project or lockfile. The protocol's host interpreter is
separate from the application runner.

The engine adoption utility inspects without running application commands,
previews a portable payload from installed engine resources, and applies only
an exact approved plan against unchanged source and targets. A common-Git lock
serializes adoption; ordinary write failure rolls back that invocation. Abrupt
interruption may leave partial files and requires inspection and a new preview.
The payload owns a separate local launcher, runtime and workflow reference.
It never rewrites the application Justfile or package metadata. Policy bindings
are explicitly merged in the request; the tool does not infer their meaning.
Semantic journal arguments infer only workspace/change identities and delegate
to the existing append owner. Advanced atomic requests retain explicit identity
inputs; neither path grants approval.

Product releases and the bundled standard Skill use one delivered source on the
branch declared in repository policy (`main` here). `release.preflight` reads that
same policy and checks clean exact source, delivered ancestry, component identities
and a supplied tag. It grants no publication authority. Manifest schema 3 binds one `repository.changes` root. It has no template version
or Specification/Plan configuration aliases; schema revisions follow wire changes
and are independent of the shared package/Skill product version.
[Releasing](../maintainers/releasing.md) owns the maintainer procedure.
