# Set up a new or existing project

Install the `signetum` plugin through the host's plugin manager:
`claude plugin marketplace add R0k1e/Signetum` and `claude plugin install
signetum@signetum`, or `codex plugin marketplace add R0k1e/Signetum` and
`codex plugin add signetum@signetum`. The marketplace pins each release to an
exact commit. The plugin carries this Skill (`signetum:signetum`) with its
execution source and dependency lock, and a Bash command guard. Remove an earlier
standalone copy in `~/.claude/skills/signetum` or `~/.codex/skills/signetum`, or
both Skills stay listed. Codex asks the user to review the plugin hook at its next
start; until then `codex exec` runs without the guard. Keep cwd in the user's
project and call `sh <skill-base-dir>/scripts/signetum ...`.

Every other agent tool (for example OpenClaw, Grok, Gemini CLI or Cursor) uses
the plain Skill: this same folder as an ordinary Agent Skill directory. Unpack
`signetum-skill-<version>.zip` from a release, or copy
`plugins/signetum/skills/signetum` from a checkout, into the tool's skills
directory as `signetum`, or point the tool at that folder. Claude Code and Codex
users install the plugin and must not also install the plain Skill. The plain
Skill has no command guard. Its protocol guarantees are unchanged: receipts bind
evidence to exact sources, and `batch-deliver` is the only operation that
advances the delivery branch. The guard only adds early refusal of work-losing
commands, so follow the same command rules without it.

## Prepare the Skill once

Check Git 2.7 or newer for Signetum's own commands, Mise, Worktrunk 0.74
(`wt`), uv and host Python 3.12+. Cleanup through Worktrunk needs Git 2.17.
Worktrunk 0.75 or newer needs Git 2.43. Report missing tools
and resolve setup explicitly. Honor the host's Mise trust decision; never trust
project configuration automatically. Run `setup` to select host Python 3.12 and uv 0.12.2 explicitly through Mise,
including on hosts with unconfigured shims, and create a locked environment in `${XDG_DATA_HOME:-~/.local/share}/signetum/runtime/<fingerprint>`.
Every installed copy of the same engine shares it, and nothing is written into the
plugin directory, which Codex hashes for hook trust. `identity` reports its
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
   fail readiness. The editing worktree stays. An environment failure is not
   permission to weaken application checks.

Normal adoption writes `signetum.toml` and enables the plugin at project scope:
`enabledPlugins` and the `signetum` marketplace in `.claude/settings.json`, and
`[plugins."signetum@signetum"] enabled = true` in `.codex/config.toml`, keeping
their other settings. The guard then applies in that repository for every
collaborator; Codex reads the project layer only for a trusted project and an
installed plugin. No required AGENTS/CLAUDE pointer,
architecture scaffolding, wrapper or copied engine is added. Legacy generated
files may be retired only through explicit exact-hash entries in the same reviewed
preview; changed and unmanaged files remain untouched. This retirement path does
not provide an old runtime fallback. Inspect interrupted application before retry.

## Update the plugin or plain Skill

This is the only update procedure. Other pages cite it.

`sh <skill-base-dir>/scripts/signetum update` reads the release pinned in the
marketplace on `main`, downloads that Skill and verifies it against the release
metadata, prepares its environment and checks the project's `signetum.toml`.
The Skill's location decides what follows and is reported as `install`. A Skill
inside the `signetum` plugin tree is a plugin install: update upgrades every
host that has `signetum@signetum` installed through its
own plugin manager: `claude plugin marketplace update signetum` and
`claude plugin update signetum@signetum`; `codex plugin marketplace upgrade
signetum` and `codex plugin add signetum@signetum`. If the Codex user setting
disabled the plugin, it stays disabled. Restart the sessions afterwards and
review the Codex hook again (`codex_hook_review_required`). Any other folder is
a plain install: update stages the verified release beside it, swaps the folder
in place, verifies the result and runs no host command; restart the tool's
sessions. A plain Skill inside a Git work tree, such as a project-local copy or
a tool pointed at a checkout, is refused; update it through that repository and
run `setup`. Update when no Agent session is working: Codex deletes the old
version directory at once, and a plain swap replaces the running folder. `identity`
reports complete Skill content and actual engine/dependency identity. Project
configuration stays manifest format 5 and protocol 2, with no engine
implementation pin. Omitted evidence fields mean the published evidence protocol
and schema digest.

- `update --check` compares the pinned release without preparing or upgrading.
  Offline, unavailable and no-release results are not up-to-date claims.
- An installed Skill with the pinned digest, or a newer one, is left unchanged.
- There is no other install path and no `--to` or `--source`. Develop against
  a checkout with `claude --plugin-dir plugins/signetum` or a local Codex
  marketplace.

Compatible implementation changes require no project edit or commit. Verification
still records actual runtime identity, so old-runtime evidence cannot qualify a
new runtime. Changed configuration/protocol contracts return migration_required
before any host is upgraded or plain folder replaced, and without editing the project. Migrate required
bindings and callers through a separately approved adoption preview, qualify and
deliver, then run `update` again. Existing active workspaces and receipts
are not automatically migrated.

For the one-time v4-to-v5 configuration migration, set schema_version to 5 and
remove signetum.engine_digest; preserve unrelated project commands and inputs.
The engine remains in the installed Skill. Do not add an application dependency.
