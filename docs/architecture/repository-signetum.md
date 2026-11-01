# Implementation and distribution

`skills/signetum` is the standard public Skill and the sole distributed execution
source. Its `scripts/engine` project has its own locked production dependencies;
the root project is only the maintainer development environment. Application
runners and delivery targets remain repository-owned. Updates are explicit.

## Maintained owners

| Owner | Responsibility |
| --- | --- |
| `commands`, `cli`, `change_cli`, `operation_cli`, `workflow_status` | Dispatch, structured results and derived views. |
| `change_record`, `development_log`, `development_store`, `decision_clauses`, `decision_history` | Approved outcomes, significant atomic journal mutations and the derived decision set. |
| `change/*`, `traceability/*`, `source_authority`, `execution_review` | Scope, immutable source proofs, accounting and review qualification. |
| `lifecycle`, `lifecycle_validation`, `workspace_operations`, `workspaces`, `provenance`, `delivery`, `synchronization` | Isolated work, named integration and exact remote-first delivery. |
| `validation/*`, `preparation`, `worktrunk`, `git` | One supervised execution/verdict owner, preparation, tool identities and Git effects. |
| `profiles/*`, `manifest`, `resources/profiles` | Explicit capability composition and validation bindings. |
| `repository_selection`, `selection_*`, `test_scheduling`, `pytest_scheduling`, `ci_partitions` | Optional source-bound optimization; no second runner or receipt authority. |
| `adoption`, `runtime_identity`, Skill `scripts/launch.py` | Exact reviewed bindings, code identity and isolated locked execution. |
| `resources/schemas`, `skill_identity`, `runtime_identity` | Installed schemas, complete Skill identity and runtime identity. |
| Root `tools/release`, `tools/site`, `tools/product_surface`, `tools/cli` | Repository-only packaging, Pages and public asset checks; excluded from the Skill. |

## One maintained implementation

`skills/signetum/scripts/engine/signetum` is the only engine source. The Skill
launcher explicitly prepares a noneditable installation under its own ignored
`.runtime/` directory using `scripts/engine/uv.lock`. Setup selects host Python 3.12 and uv 0.12.2 through Mise; a prepared launcher uses that
interpreter directly instead of selecting the application’s Python. Normal commands verify
the installed environment and supported project contracts; they never install or
repair tooling. The application environment is not the engine environment. The launcher forwards arguments unchanged; `commands` owns the sole public
registry used by CLI/help and installed acceptance. Eight lifecycle operations
are direct; `change`, `test`, `check`, `adopt` and `maintenance` own auxiliary
work. No public lifecycle/protocol namespace or validate alias remains. Bootstrap
setup, identity and explicit updates are declared alongside the command table.
`identity` reports complete Skill and actual engine identities. `scripts/update.py`
owns explicit acquisition, compatibility inspection and atomic installation switching.
`scripts/installation.py` protects active installations with shared/exclusive guards.
Verified versions stay outside projects under the user data directory; the installed
Skill entry selects one version. Compatible implementation updates change only that
installation; project edits are reserved for contract migrations.


Root `uv.lock` pins maintainer tools and an editable engine dependency. Internal
wheel/sdist builds verify the install boundary; the standard Skill folder is the
user distribution unit. It contains source and the runtime lock, never caches,
virtual environments, generated evidence or another bundled Skill copy. Pure
rules run once in core tests; installed-Skill traversals protect real adoption,
preparation, hooks, failures, integration and delivery boundaries.

## Records and authority

One approved change owns outcomes, acceptance, exclusions and autonomy. Execution
steps cannot narrow that contract. Significant source history lives in
`changes/<id>/events.jsonl`, written only by its locked owner. Expected approval
and history digests, immutable source proofs, protected committed prefixes and
atomic replacement prevent stale or partial reinterpretation. Exact retries are
idempotent; refused requests append nothing.

Current clause decisions are derived. Accepted standalone cross-change authorities
retain their original basis. Historical ledgers/documents are read-only evidence,
not fallback approval or another authoring path. Retractions and exact approved
evidence retirements preserve earlier statements and provenance. Never hand-edit
JSON Lines, invent historical acceptance or maintain another decision summary.

## Adoption and customization

Inspection and preview execute no application command. Apply requires the exact
reviewed plan and unchanged source/targets, preserves unrelated files and rolls
back ordinary write failure. An interrupted write requires inspection and a fresh
preview. Normal adoption writes only `signetum.toml`. Agent entry files and architecture
are optional existing context. Explicit hash-bound retirement may remove known
old generated files; changed/unmanaged files are preserved. The Skill launcher
downloads and updates nothing during ordinary work.

Profiles declare versioned capabilities and dependencies, reject conflicts and
bind resolved identities into evidence. Repository tools/shards/gates explicitly
select execution. Existing-runner adapters preserve argv, deadlines and native
metadata; they do not infer languages or install application tools. Host Python
is separate from an application's language. See [the guide](../guide.md) and
[runner bindings](../guides/existing-runners.md).

Keep affected architecture and instructions current in the implementing change.
Reasons belong once in its significant history. Current pages describe actual
owners; they are not an exhaustive algorithm catalogue or execution diary.

## Source and disposable material

Keep public Skill instructions, its engine source/lock, installable schemas,
product site and brand assets in source. Design tools, screenshots, caches,
environments, built packages, receipt logs and test reports are disposable local
outputs. Acceptance fixtures are internal test material, never application
scaffolding copied by adoption. Current architecture and guides describe owners;
consequential reasons belong once in the change journal or accepted decision.

The optional selection interface is language-neutral. Projects own algorithms
and family rules; no application-specific dependency selector is bundled.
Self-use runs the complete member gate. Core verifies source/target identity and
preserves full final validation. `development_store` owns locked record storage,
`development_log` owns projection and `workflow_status` owns derived workspace state.
