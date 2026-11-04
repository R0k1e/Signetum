# Signetum

<p align="center">
  <img src="assets/brand/signetum-mark.png" width="80" alt="Signetum signet">
</p>

**A protocol for reliable agentic development and delivery.**

Keep key decisions, coordinate independent Agent work, validate the integrated
result and deliver the source you checked. Signetum supports evolving repositories,
from one Agent across sessions to parallel Agent development. One plugin for
Claude Code and Codex carries the Skill that guides new projects and existing
repositories using their own application tools, and a guard that refuses shell
commands which lose work or bypass the protocol.

## Install and start

Install the `signetum` plugin with your host's plugin manager. Each release pins
an exact commit:

```sh
claude plugin marketplace add R0k1e/Signetum
claude plugin install signetum@signetum
codex plugin marketplace add R0k1e/Signetum
codex plugin add signetum@signetum
```

Codex asks you to review the plugin's command hook at its next start. The Skill
is `signetum:signetum`. If you installed the earlier standalone Skill, remove
`~/.claude/skills/signetum` and `~/.codex/skills/signetum` so only one remains.
Installation does not change previously adopted repositories.

Other agent tools, such as OpenClaw, Grok, Gemini CLI or Cursor, use the plain
Skill: unpack `signetum-skill-<version>.zip` from a release, or copy
`plugins/signetum/skills/signetum`, into the tool's skills directory as
`signetum`. Claude Code and Codex users install the plugin instead and must not
also install the plain Skill. The plain Skill has no command guard; receipts and
`batch-deliver`, the only operation that advances the delivery branch, still
carry the protocol guarantees, and the guard only refuses work-losing commands
early. `update` replaces a plain Skill folder in place.

Then ask:

> Use Signetum to set up this new project, or inspect and adopt this existing
> repository. Preserve its tools and show the proposed changes first.

The agent prepares the installed Skill's locked execution environment, inspects
the project and proposes `signetum.toml` bindings and the project settings that
enable the plugin there. You review the preview.
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

`main` owns the plugin and its standard Skill, including the execution source,
lock and guard, plus maintainer tests and documentation. The plugin is the
distribution unit;
internal package builds verify its isolated installation boundary. Consumer
projects retain only their reviewed bindings and development records.

[Documentation](docs/README.md) covers usage and configuration.
[Architecture](docs/ARCHITECTURE.md), [Contributing](CONTRIBUTING.md) and
[releasing](docs/maintainers/releasing.md) describe maintenance.
[Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [Apache-2.0](LICENSE)
