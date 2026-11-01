# Set up a new or existing project

Install the complete `signetum` Skill folder from an exact reviewed tag or commit.
It includes instructions, execution source and its dependency lock. Keep cwd in
the user's project and call `sh <skill-base-dir>/scripts/signetum ...`.

## Prepare the Skill once

Check Git 2.7 or newer for Signetum's own commands, Mise, Worktrunk 0.74
(`wt`), uv and host Python 3.12+. Cleanup through Worktrunk needs Git 2.17.
Worktrunk 0.75 or newer needs Git 2.43. Report missing tools
and resolve setup explicitly. Honor the host's Mise trust decision; never trust
project configuration automatically. Run `setup` to select host Python 3.12 and uv 0.12.2 explicitly through Mise,
including on hosts with unconfigured shims, and create a locked environment under the installed Skill's ignored `.runtime/` directory. `identity` reports its
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

## Update an installed Skill

This is the only update procedure. Other pages cite it.

Bare `sh <skill-base-dir>/scripts/signetum update` installs the latest eligible
stable Signetum release and prepares that candidate. It does not ask for a
separate setup of the old environment. `identity` reports complete Skill content
and actual engine/dependency identity. Project configuration stays manifest
format 5 and protocol 2, with no engine implementation pin. Omitted evidence
fields mean the published evidence protocol and schema digest.

- `update --check` reads eligible stable release metadata, or compares
  `--source <complete-skill-directory>`, without preparing or switching.
  Historical RepoSeal releases, drafts and prereleases do not imply an upgrade.
  Offline, unavailable and no-release results are not up-to-date claims.
- `update --to <version-or-commit>` installs that exact release version or
  commit. `update --source <complete-skill-directory>` installs a local
  candidate. Moving branch names are refused; remote versions resolve to
  immutable commits.
- An already-current stable release, or an older one, returns without replacing
  the installation.

Version directories stay immutable outside application repositories. An upgrade
switches only the install entry, after the candidate is prepared and the current
project contract is checked. It does not overwrite a Git-managed source checkout
or rewrite a version directory. A command that already resolved an old version
keeps that directory; switching the entry does not wait for it to finish.
Preparation, network or switch failure leaves the old entry usable.
`previous_entry` identifies the retained version. Do not delete versions used by
other workspaces. Commands other than `update` never download or upgrade.

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
