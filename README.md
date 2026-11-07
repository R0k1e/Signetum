# Signetum

<p align="center">
  <img src="assets/brand/signetum-mark.png" width="80" alt="Signetum signet">
</p>

**A protocol for reliable agentic development and delivery.**

Keep key decisions, coordinate independent Agent work, validate the integrated
result and deliver the source you checked. Signetum supports evolving repositories,
from one Agent across sessions to parallel Agent development. One standard Agent
Skill guides new projects and existing repositories using their own application
tools, in any agent tool. It carries an optional guard that refuses shell commands
which lose work or bypass the protocol.

## Install and start

Unpack `signetum-skill-<version>.zip` from the
[latest release](https://github.com/R0k1e/Signetum/releases/latest) into your
agent tool's skills directory as `signetum`, for example `~/.claude/skills` for
Claude Code or `~/.codex/skills` for Codex, or copy `skills/signetum` from a
checkout. That folder is a complete install in any tool. Installation does not
change previously adopted repositories.

Optionally register the command guard, a PreToolUse hook that refuses
work-losing commands early in repositories with `signetum.toml`:

```sh
sh ~/.claude/skills/signetum/scripts/signetum setup
sh ~/.claude/skills/signetum/scripts/signetum install --host claude --host codex
```

`install` places the Skill for each host and adds the hook to Claude Code's
`settings.json` and Codex's `hooks.json`; `--preview` shows the plan and
`--remove` reverses it. Codex asks once to review the new hook. Without the
guard, receipts and `batch-deliver`, the only operation that advances the
delivery branch, still carry the protocol guarantees. `update` replaces the
Skill folder in place from the newest release.

Coming from the `signetum@signetum` plugin? Run the `install` command above: it
removes a user-scope plugin after the Skill and hook are in place and lists any
project-scope plugin with its removal command. Then run
`claude plugin marketplace remove signetum` and `codex plugin marketplace remove
signetum`, and remove the plugin entries earlier adoption wrote to project
`.claude/settings.json` and `.codex/config.toml`. See
[the migration notes](skills/signetum/references/adoption.md#migrate-from-the-plugin).

Then ask:

> Use Signetum to set up this new project, or inspect and adopt this existing
> repository. Preserve its tools and show the proposed changes first.

The agent prepares the installed Skill's locked execution environment, inspects
the project and proposes `signetum.toml` bindings. You review the preview.
Execution stays with the Skill; application dependencies and Agent entry files
stay unchanged. Daily work needs no upstream checkout or tool downloads.
See [First use](QUICKSTART.md).

For a development task, describe the behavior normally. Discuss consequential
choices with the agent, then approve the outcome and acceptance. For parallel
work, agree on task boundaries, dependencies, shared interfaces and an integration
owner. You or your coding-agent host organize the agents; each member develops
in an isolated worktree. Qualified changes enter a named batch for complete
validation and explicit delivery.

## What it gives you

- Key decisions and their basis kept once, with a derived current decision set.
- Clear ownership, dependencies and isolated worktrees for parallel agent changes.
- Named integration, complete final checks and delivery of the exact checked source.
- Preserved first failures and inspected recovery after delivery interruptions.
- Behavioral tests through existing tools; optional project selectors and bounded
  test scheduling can improve feedback without weakening final validation.

The runtime is language-neutral and uses a host Python interpreter. It can retain
Python, Node, Rust or other application runners. Signetum is a development and
delivery protocol, not an automatic global agent or machine-resource scheduler.
It provides no remote ledger or automatic consumer updates.

## Maintained source

`main` owns the standard Skill, including the execution source, lock and guard,
plus maintainer tests and documentation. The Skill folder is the distribution
unit; internal package builds verify its isolated installation boundary. Consumer
projects retain only their reviewed bindings and development records.

[Documentation](docs/README.md) covers usage and configuration.
[Architecture](docs/ARCHITECTURE.md), [Contributing](CONTRIBUTING.md) and
[releasing](docs/maintainers/releasing.md) describe maintenance.
[Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [Apache-2.0](LICENSE)
