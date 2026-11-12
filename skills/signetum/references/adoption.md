# Set up a new or existing project

The Skill folder is the whole product. Unpack `signetum-skill-<version>.zip` from
a [release](https://github.com/R0k1e/Signetum/releases), or copy `skills/signetum`
from a checkout, into the agent tool's skills directory as `signetum`, or point
the tool at that folder: `~/.claude/skills` for Claude Code, `~/.codex/skills`
for Codex, the tool's own directory elsewhere. That is a complete install. Keep
cwd in the user's project and call `sh <skill-base-dir>/scripts/signetum ...`.
A host loads one Signetum Skill; do not keep a second copy or the earlier
`signetum@signetum` plugin next to it.

The command guard is optional. Without it the protocol guarantees are unchanged:
receipts bind evidence to exact sources, and `batch-deliver` is the only
operation that advances the delivery branch. The guard only refuses work-losing
commands early, so follow the same command rules without it. It is a PreToolUse
hook entry in the host's own configuration that runs the Skill's
`scripts/command-guard`; it applies in Git work trees whose root holds
`signetum.toml` and allows everything elsewhere. A guard that cannot run allows
the command; it prevents mistakes and is not a security boundary.

## Install command

After `setup`, `install` places the Skill and registers the guard in one step:

```sh
sh <skill-base-dir>/scripts/signetum install --host claude --host codex
```

`--host claude` places the Skill in `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/signetum`
and adds one guard entry to that directory's `settings.json`; `--host codex` uses
`${CODEX_HOME:-~/.codex}/skills/signetum` and `hooks.json`. `--skills-dir <dir>`
places only the Skill, as `<dir>/signetum`, for any other tool; add the hook entry
by hand where that tool reads hooks. The source is the running Skill unless
`--source <folder-or-zip>` or `--release <tag>|latest` names another; a release
is verified like `update`. Other settings and hooks are kept, and only Signetum
guard entries are replaced. `--preview` reports the exact plan and writes
nothing; a repeated run reports `unchanged`; `--remove` deletes the guard entries
and the placed Skill. Install refuses a folder that is not a Signetum Skill or
lies inside a Git work tree, and never edits a project. Restart the host sessions
afterwards. Codex asks once to review the new hook
(`codex_hook_review_required`); the entry names a stable path, so updates do not
ask again.

When the running Skill sits in a Claude Code or Codex user skills directory and
no hook runs its guard, `status` reports a `guard` entry with the install command
and the exact hook entry to add by hand. Mention it to the user once; it is
guidance and never blocks an operation.

### Migrate from the plugin

Signetum 0.4 and earlier shipped as the `signetum@signetum` plugin. Run `install`
for each host that has it. After the Skill and hook are in place, install removes a
user-scope plugin through the host (`claude plugin uninstall signetum@signetum
--scope user`, `codex plugin remove signetum@signetum`) and reports a project-scope
Claude plugin with its command instead of running it. Then remove the
marketplace (`claude plugin marketplace remove signetum`, `codex plugin
marketplace remove signetum`) and, through each project's own reviewed change,
the `enabledPlugins` and `extraKnownMarketplaces` `signetum` entries in
`.claude/settings.json` and the `[plugins."signetum@signetum"]` table in
`.codex/config.toml` that earlier adoption wrote.

## Prepare the Skill once

Check Git 2.7 or newer for Signetum's own commands, Mise, Worktrunk 0.74
(`wt`), uv and host Python 3.12+. Cleanup through Worktrunk needs Git 2.17.
Worktrunk 0.75 or newer needs Git 2.43. Report missing tools
and resolve setup explicitly. Honor the host's Mise trust decision; never trust
project configuration automatically. Run `setup` to select host Python 3.12 and uv 0.12.2 explicitly through Mise,
including on hosts with unconfigured shims, and create a locked environment in `${XDG_DATA_HOME:-~/.local/share}/signetum/runtime/<fingerprint>`.
Every installed copy of the same engine shares it, and nothing is written into the
Skill directory, so its content digest stays the released one. `identity` reports its
code and dependency identities. No Signetum dependency belongs in the application's
production or development dependency groups. Declared application commands run
through `mise exec --` after Git repository context and `PYTHONPATH`,
`PYTHONHOME`, `VIRTUAL_ENV`, and `UV_PROJECT_ENVIRONMENT` are removed. The Skill
engine environment is not prepended onto their PATH.

Prepared operations use the Skill’s own bootstrap interpreter, regardless of
the application’s Python version or tool selection.
Ordinary operations refuse an absent, changed or incompatible environment with a
setup/update action. They never clone, install, sync or repair the Skill. Do not
copy the generated environment into a distribution artifact. An upstream checkout is unnecessary for daily work.

## Review project bindings

For a new project, initialize its ordinary application files and Git history.
For an existing one, preserve tools, metadata, locks, entry files and decisions.
Both use the same adoption flow:

1. `adopt inspect` reports tool presence, the version printed by `name --version`,
   Git floors (2.7 for Signetum's own commands and 2.17 for Worktrunk cleanup),
   and both the PATH `uv` version and `mise exec -- uv --version` when Mise is
   present. A version difference is reported and does not fail inspection.
   Inspect runs no application command and does not modify the project.
2. Prepare one request containing the complete reviewed `signetum.toml` text.
   Bind supported configuration/protocol versions, delivery branch, record roots, actual tool
   identities, inputs and preparation/member/batch/final commands. Architecture
   is optional context. See the [binding contract](https://github.com/R0k1e/Signetum/blob/main/docs/guides/existing-runners.md).
   The delivery branch is the one branch `batch-deliver` advances. Workspace and
   batch operations read it from `[delivery] branch`, and `ready` and `final`
   check against the bases taken from it, so every operation agrees on one base.
   Changing it is one edit to that binding.
3. `adopt preview --repository . --request <request.json> --output <plan.json>`
   captures the source and exact before/after bytes. Show the user that preview.
4. Apply the approved plan with `adopt apply --repository . --plan <plan.json>
   --expected-plan <digest>`. Changed source or targets require a fresh preview.
5. Commit through the project's existing process and exercise a small authorized
   change through `ready`. Ready prepares and checks a temporary detached checkout
   of the committed tip. An ignored file that preparation needs and that is not
   in the commit fails ready. An ignored file preparation does not need does not
   fail readiness. The editing worktree stays. A prepare shard may rebuild stale
   ignored or derived state and continue; Signetum accepts it when it exits zero
   with tracked source unchanged, and a failure names the shard, its command and
   the adapter's `expected` from its last JSON output line. An environment failure
   is not permission to weaken application checks.

Normal adoption writes only `signetum.toml`; it changes no host settings. No required AGENTS/CLAUDE pointer,
architecture scaffolding, wrapper or copied engine is added. Legacy generated
files may be retired only through explicit exact-hash entries in the same reviewed
preview; changed and unmanaged files remain untouched. This retirement path does
not provide an old runtime fallback. Inspect interrupted application before retry.

## Update the Skill

This is the only update procedure. Other pages cite it.

`sh <skill-base-dir>/scripts/signetum update` resolves the newest published
release, downloads its Skill archive, `release-source.json` and `SHA256SUMS`,
verifies the checksums and the extracted Skill's version and content digest
against the release metadata, prepares its environment and checks the project's
`signetum.toml`. It then replaces the Skill folder in place from a staged sibling
copy, verifies the result and runs no host command; restart the tool's sessions.
Hook entries name the folder's stable path, so they keep working and need no
review. A Skill inside a Git work tree, such as a copy committed to a project or
a checkout a tool points at, is refused; update it through that repository and
run `setup`. Update when no Agent session is working, because the swap replaces
the running folder. `identity` reports complete Skill content and actual
engine/dependency identity. New project configuration uses manifest format 6 and
protocol 2; format 5 remains readable, with no project-level engine implementation pin. Batches separately record their
opening engine. Omitted evidence fields mean the
published evidence protocol and schema digest.

- `update --check` compares the newest release without preparing or replacing.
  Offline, unavailable and no-release results are not up-to-date claims.
- An installed Skill with the released digest, or a newer one, is left unchanged.
- `install --release <tag>` places a specific published release.

Compatible implementation changes require no project edit or commit. Verification
still records actual runtime identity. Members remain unpinned; batch operations
require the recorded batch engine. Changed configuration/protocol contracts return migration_required
before the folder is replaced, and without editing the project. Migrate required
bindings and callers through a separately approved adoption preview, qualify and
deliver, then run `update` again. Existing active workspaces and receipts
are not automatically migrated.

For the one-time v4-to-v5 configuration migration, set schema_version to 5 and
remove signetum.engine_digest; preserve unrelated project commands and inputs.
The engine remains in the installed Skill. Do not add an application dependency.

Operate consumer repositories through the installed Skill launcher, for example
`sh ~/.claude/skills/signetum/scripts/signetum <operation>`. Project wrappers
set `SIGNETUM_SKILL` and call that launcher's `scripts/signetum`; they never
call an engine in another development checkout. Update the Skill only when no
batch is open. A batch pins the opening engine; finish it with that engine or
open a new batch for the same ready members. Publishing a newer release leaves
an open batch's installed engine and pin in place. Repository self-hosting runs
batch operations from the batch worktree with its own engine. When that
checked-out engine rejects `--message-file`, adopt the qualified repository
engine in the batch before admission. The source is an approved Ready commit in
this repository, the caller message is kept, and the pin stays `repository`.
An interrupted handoff retries the recorded object.

A project that owns `core.hooksPath` should chain the machine-local Signetum
shim from its `reference-transaction` hook:

```sh
input=$(cat)
shim="$(git rev-parse --git-common-dir)/signetum/hooks/reference-transaction"
if [ -x "$shim" ]; then printf '%s\n' "$input" | "$shim" "$@" || exit $?; fi
```

Preparation verifies the effective chain with a real Git probe. Check status for
`commit_check.status`: an inactive check warns with its cause and chaining
snippet; ready and final still judge immutable commit attribution.

## Upgrade to 0.8

Update the installed Skill only when no batch is open and restart sessions. The
update result includes migration guidance. Format-5 configuration and format-1
change records remain readable: keep historical approvals and journals intact,
including approval digests, pending observations and old failure receipts. Old
digests and owed ledgers are ignored; observations appear in unfinished work.
In a member, change signetum.toml to schema_version 6; use change schema_version 2
for new records and approval fields actor, recorded_at and a neutral statement.
Never quote the owner verbatim. Scope revisions are recorded without re-approval.
Repository commands continue to own environment preparation and full final test
selection. Run ready and then final on an authorized integrated batch; delivery
still requires explicit owner authorization. Do not edit a consumer as part of
updating the Skill.
