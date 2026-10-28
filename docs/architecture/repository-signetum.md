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
The generated package is standard-library code; adapters own repository effects.

| Shared authority | Responsibility |
| --- | --- |
| `delivery` | Remote-first publication and exact interrupted-publication recovery after adapter-owned qualification. |
| `operations`, `git`, `workspaces` | Operation values, isolated Git context and immutable workspace/change records. |
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
`requires_final` never substitutes for missing member checks. Native Linux/macOS
resource observations and explicit host-adapter observations consume the same
budget algorithm.

[Tooling alignment](../../changes/align-perdura-development-tooling/specs/tooling.toml)
still owns the remaining manifest/profile normalization, lifecycle orchestration
and durable change-authority migration. Shared validation modules alone do not
complete that change.
