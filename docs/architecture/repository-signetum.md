# Implementation and distribution

The standard Skill `skills/signetum` is the one distributed unit for every agent
tool and the sole distributed execution source; a release publishes it as
`signetum-skill-<version>.zip`. Its `scripts/engine` project has its own locked
production dependencies; the root project is only the maintainer development
environment. Application runners and delivery targets remain repository-owned.
There is no plugin manifest, marketplace or release pin: a host reads the Skill
from its skills directory and the optional guard from its own hook configuration.
Updates are explicit; no second Skill copy exists in the repository.

## Maintained owners

| Owner | Responsibility |
| --- | --- |
| `commands`, `cli`, `change_cli`, `operation_cli`, `workflow_status` | Dispatch, structured results and derived views. |
| `change_record`, `development_log`, `development_store`, `decision_clauses`, `decision_history` | Approved outcomes, significant atomic journal mutations and the derived decision set. |
| `change/*`, `traceability/*`, `source_authority`, `execution_review` | Scope, immutable source proofs, accounting and review qualification. |
| `lifecycle`, `lifecycle_validation`, `workspace_operations`, `workspaces`, `provenance`, `delivery`, `synchronization`, `gate_records` | Isolated work, named integration, machine-local gate memory and exact remote-first delivery. |
| `validation/*`, `preparation`, `worktrunk`, `git` | One supervised execution/verdict owner, preparation, tool identities and Git effects. |
| `profiles/*`, `manifest`, `resources/profiles` | Explicit capability composition and validation bindings. |
| `repository_selection`, `selection_*`, `test_scheduling`, `pytest_scheduling`, `ci_partitions` | Optional source-bound optimization; no second runner or receipt authority. |
| `adoption`, `runtime_identity`, `engine_pin`, Skill `scripts/launch.py` | Exact reviewed bindings, code identity, batch engine pins and isolated locked execution. |
| Skill `scripts/command_guard.py`, `scripts/command-guard` | The stdlib-only PreToolUse guard. |
| Skill `scripts/distribution.py`, `hosts` | Install and update: release verification, staged folder replacement, host hook entries and status guidance. |
| `commit_check` | Stable commit-check shim, effective hook-chain probing and the immutable verdict entry. |
| `resources/schemas`, `skill_identity`, `runtime_identity` | Installed schemas, complete Skill identity and runtime identity. |
| Root `tools/release`, `tools/site`, `tools/product_surface`, `tools/cli` | Repository-only packaging, Pages and public asset checks; excluded from the Skill. |

## One maintained implementation

`skills/signetum/scripts/engine/signetum` is the only engine
source. The Skill launcher explicitly prepares a noneditable installation in
`${XDG_DATA_HOME:-~/.local/share}/signetum/runtime/<fingerprint>` using
`scripts/engine/uv.lock`. The fingerprint covers the implementation digest, the
lock and `pyproject.toml`, not the install path, so the Claude copy, the Codex copy
and an update candidate share one environment; `runtime/host-python` only starts
the launcher. Nothing is written into the Skill directory, so its content digest
stays the released one. Setup selects host Python 3.12 and uv 0.12.2 through Mise; a prepared launcher uses that
interpreter directly instead of selecting the application’s Python. Tools the
engine runs through Mise, such as Worktrunk's `wt`, run under the caller's
`MISE_ENV`; when a tool is missing there and exactly one Mise environment the
project declares (`mise.<env>.toml` and Mise's other environment file forms)
provides it, the engine sets that `MISE_ENV`, and otherwise its refusal names
the tool and the declared environments. Batch operations use the engine recorded at batch-open. Self-hosting pins the
batch worktree location; installed Skills pin version and implementation.
Foreign checkout engines cannot open consumer batches. Normal commands verify
the installed environment and supported project contracts; they never install or
repair tooling. The application environment is not the engine environment. The launcher forwards arguments unchanged; `commands` owns the sole public
registry used by CLI/help and installed acceptance. Seven lifecycle operations
are direct; `change`, `test`, `check`, `adopt` and `maintenance` own auxiliary
work. No public lifecycle/protocol namespace or validate alias remains. Bootstrap
setup, identity and explicit updates are declared alongside the command table.
`identity` reports complete Skill and actual engine identities.
`scripts/distribution.py` owns `install` and `update`. Both read published GitHub
releases only: the newest through the releases API or an exact tag, verified
against `SHA256SUMS` and `release-source.json` before the extracted Skill's version
and content digest are accepted. `update` prepares the candidate, checks the
project manifest and swaps the Skill folder in place from a staged sibling copy;
`install` places a Skill for `--host claude|codex` or `--skills-dir` and writes one
guard entry into the host's user hook configuration (`settings.json` or
`hooks.json`) through the engine's stdlib `hosts` module, replacing only Signetum
guard entries. Both refuse a folder inside a Git work tree and never edit a
project. Install removes an earlier user-scope `signetum@signetum` plugin through
the host after the Skill and hook are in place. `scripts/installation.py`
gives running commands a shared lock on their environment and setup an exclusive
one. Compatible implementation updates change only the installation; project
edits are reserved for contract migrations.

The guard reads `tool_input.command` and `cwd` from Claude Code and Codex payloads,
splits the command into simple commands and exits 2 with one JSON line naming the
category and the Signetum operation to use. It applies only when the payload cwd
lies in a Git work tree whose root holds `signetum.toml`, so one user-level hook
covers exactly the adopted repositories. A guard that cannot run allows the
command. When the running Skill sits in a Claude Code or Codex user skills
directory and no hook runs its guard, `status` reports a `guard` entry with the
install command and hook entry; it never blocks. The
guard only refuses early; receipts and `batch-deliver` as the only operation
that advances the delivery branch carry the guarantees, with or without it.


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
idempotent; refused requests append nothing. Writes serialize per worktree through
`signetum-journal.lock` in that worktree's Git directory: other worktrees never
wait, and a second writer in the same worktree waits up to two minutes. The
semantic `resolve` takes the observation ID or the record's `--id` as its target
and writes a pytest node id `path::test` as its file path. `change why <clause>`
gathers one clause's accepted revisions, reasons, owning approvals and commits;
`status` lists unresolved observations with counts by status, and `--verbose`
adds resolved ones.

Current clause decisions are derived. Accepted standalone cross-change authorities
retain their original basis. Historical ledgers/documents are read-only evidence,
not fallback approval or another authoring path. Retractions and exact approved
evidence retirements preserve earlier statements and provenance. Never hand-edit
JSON Lines, invent historical acceptance or maintain another decision summary.

## Adoption and customization

Inspection and preview execute no application command. Apply requires the exact
reviewed plan and unchanged source/targets, preserves unrelated files and rolls
back ordinary write failure. An interrupted write requires inspection and a fresh
preview. Normal adoption writes `signetum.toml` and enables `signetum@signetum` at
project scope in `.claude/settings.json` and `.codex/config.toml`, preserving their
other settings. Agent entry files and architecture
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
