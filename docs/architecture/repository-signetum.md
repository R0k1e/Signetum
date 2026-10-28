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
| `operations`, `git`, `workspaces` | Operation values, isolated Git context and immutable workspace/change records. |
| `worktrunk` | Supervised Mise execution, repository environment projection and registered workspace inventory parsing. |
| `preparation` | Configured preparation execution with clean or staged-state guards and unchanged source identity. |
| `operation_cli` | Shared argument refusals, result categories and retained operation diagnostics. |
| `contract_values`, `change.models`, `traceability`, `status` | Frozen change values, native and wire constraints, complete relation checks and derived status. |
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
