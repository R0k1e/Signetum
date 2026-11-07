# First use

Unpack `signetum-skill-<version>.zip` from the
[latest release](https://github.com/R0k1e/Signetum/releases/latest) into your
agent tool's skills directory as `signetum` (`~/.claude/skills` for Claude Code,
`~/.codex/skills` for Codex, the tool's own directory elsewhere). That is a
complete install; installation supplies instructions and an optional command
guard, not a project workflow. Keep one Signetum Skill per host.

To enable the guard, run `sh <skill>/scripts/signetum setup` and then
`sh <skill>/scripts/signetum install --host claude` (or `--host codex`). It adds a
PreToolUse hook that refuses work-losing commands early in repositories with
`signetum.toml`; Codex asks once to review it. Without the guard, receipts and
`batch-deliver` still carry the protocol guarantees. When the guard is missing,
the agent mentions how to enable it once. Users of the earlier
`signetum@signetum` plugin follow
[the migration notes](skills/signetum/references/adoption.md#migrate-from-the-plugin).

## Ask the agent to set up your project

For a new project:

> Use Signetum to initialize [project]. Use [our chosen tools], prepare the
> local development protocol, and show the setup changes before applying them.

For an existing repository:

> Use Signetum to inspect and adopt this repository. Preserve our tools,
> architecture and accepted decisions. Show the proposed changes first.

The agent checks prerequisites and explicitly prepares the installed Skill’s locked
execution environment.
It initializes a new project's ordinary files or inspects existing authorities,
then uses the same adoption preview. You review source, scope and changes; the
agent handles request formats and commands. Missing tools or an unavailable source
are reported with the next setup action. A source must actually be available;
an unpublished development worktree is not an installable public revision.

Host execution needs Git 2.7 or newer for Signetum's own commands, Mise,
Worktrunk 0.74, uv and Python 3.12+. Cleanup through Worktrunk needs Git 2.17.
Worktrunk 0.75 or newer needs Git 2.43. Your application's language and test
framework stay unchanged. The agent reports and resolves required setup before
promising a usable workspace. You do not copy a template over the project.

Adoption adds the reviewed `signetum.toml` bindings. Host settings, Agent entry
files and application dependencies stay unchanged. Daily commands run the installed Skill in its own environment. The upstream checkout is unnecessary; updates require a
later explicit preview. No runtime is copied into your project.

## Develop and deliver reliably

> Use Signetum to implement [behavior]. Show the intended outcome, scope and
> acceptance first. Stop at ready.

The same process supports a single Agent across sessions and parallel members.
Discuss consequential choices about behavior, architecture or delivery before
implementation.
The agent should explain the alternatives, consequences and recommendation; you
confirm the intended outcome and acceptance. It opens an isolated member workspace
and keeps significant decisions once in the change history. Ordinary command
output stays in local logs.

For parallel work, ask:

> Use Signetum to divide [change] into independent tasks. Propose ownership,
> shared interfaces, dependencies and an integration owner first. Give each
> coding agent an isolated worktree and bring ready members into one named batch.

You or your coding-agent host launch and coordinate the agents. Agree on shared
interfaces before dependent edits, synchronize deliberately and let the named
integration owner resolve overlaps. Signetum supplies the protocol and workspace
boundaries; it does not automatically schedule agents or host resources.

The result names the exact commit, checks, outstanding issues and readiness.
A diagnostic retry does not clear an original failure. When you want to deliver,
request integration and full validation, then review the generated delivery
result before authorizing delivery.

The [documentation map](docs/README.md) routes configuration and operation details.

## Update the Skill

Ask the Agent to run `update`. It checks the newest release against your project
and replaces the Skill folder in place; restart the sessions afterwards. Hook
entries keep working. The one procedure is
[the update section](skills/signetum/references/adoption.md#update-the-skill).
