# Set up a new or existing project

Install the complete `signetum` Skill folder from an exact reviewed tag or commit.
It includes instructions, execution source and its dependency lock. Keep cwd in
the user's project and call `sh <skill-base-dir>/scripts/signetum ...`.

## Prepare the Skill once

Check Git, Mise, Worktrunk (`wt`), uv and host Python 3.12+. Report missing tools
and resolve setup explicitly. Honor the host's Mise trust decision; never trust
project configuration automatically. Run `setup` to select host Python 3.12 explicitly through Mise and create a locked environment
under the installed Skill's ignored `.runtime/` directory. `identity` reports its
code and dependency identities. No Signetum dependency belongs in the application's
production or development dependency groups. Application commands retain their
own environment; the engine environment is never prepended to their PATH.

Prepared operations use the Skill’s own bootstrap interpreter, regardless of
the application’s Python version or tool selection.
Ordinary operations refuse an absent, changed or incompatible environment with a
setup/update action. They never clone, install, sync or repair the Skill. Use a
writable complete Skill installation; do not copy its generated environment into
a distribution artifact. An upstream checkout is unnecessary for daily work.

## Review project bindings

For a new project, initialize its ordinary application files and Git history.
For an existing one, preserve tools, metadata, locks, entry files and decisions.
Both use the same adoption flow:

1. `adopt inspect` reports available tools and the engine digest without running
   application commands or reading/modifying Agent entrypoints.
2. Prepare one request containing the complete reviewed `signetum.toml` text.
   Bind supported configuration/protocol versions, delivery branch, record roots, actual tool
   identities, inputs and preparation/member/batch/final commands. Architecture
   is optional context. See the [binding contract](https://github.com/R0k1e/Signetum/blob/main/docs/guides/existing-runners.md).
3. `adopt preview --repository . --request <request.json> --output <plan.json>`
   captures the source and exact before/after bytes. Show the user that preview.
4. Apply the approved plan with `adopt apply --repository . --plan <plan.json>
   --expected-plan <digest>`. Changed source or targets require a fresh preview.
5. Commit through the project's existing process and exercise a small authorized
   change through `ready`. Preparation dependencies run before commands that need
   them; an environment failure is not permission to weaken application checks.

Normal adoption writes only `signetum.toml`. No required AGENTS/CLAUDE pointer,
architecture scaffolding, wrapper or copied engine is added. Legacy generated
files may be retired only through explicit exact-hash entries in the same reviewed
preview; changed and unmanaged files remain untouched. This retirement path does
not provide an old runtime fallback. Inspect interrupted application before retry.

## Explicit updates

Bare `update` shows this guide without preparing an environment or accessing the
network. `identity` reports complete Skill content and actual engine/dependency
identity. Project configuration declares manifest format 5 and protocol 2; it
contains no engine implementation pin.

- `update --check` reads eligible stable Signetum release metadata. Historical
  RepoSeal releases, drafts and prereleases do not imply an upgrade. Offline,
  unavailable and no-release results are not up-to-date claims.
- `update --check --source <complete-skill-directory>` compares a local candidate
  without preparing or switching an installation.
- `update --source <complete-skill-directory>` or `update --to <version-or-commit>`
  explicitly acquires a complete candidate, prepares and verifies its isolated
  runtime, checks current project compatibility and switches the installed entry.
  Moving branch names are refused; remote versions resolve to immutable commits.

The installer retains usable version directories outside application repositories
and switches the stable entry only after verification. Active installation use
refuses replacement. Preparation/switch failure leaves the old usable entry;
`previous_entry` identifies the retained version. Do not delete versions used by
other workspaces. Ordinary commands never download or automatically upgrade.

Compatible implementation changes require no project edit or commit. Verification
still records actual runtime identity, so old-runtime evidence cannot qualify a
new runtime. Changed configuration/protocol contracts return migration_required
without switching or editing the project. Use the candidate entry for a separately
approved adoption preview, migrate required bindings/callers, qualify and deliver,
then explicitly activate the installation. Existing active workspaces and receipts
are not automatically migrated.

For the one-time v4-to-v5 configuration migration, set schema_version to 5 and
remove signetum.engine_digest; preserve unrelated project commands and inputs.
The engine remains in the installed Skill. Do not add an application dependency.
