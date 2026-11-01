# First use

Install the standard [Signetum Skill](https://github.com/R0k1e/Signetum/tree/main/skills/signetum)
with your coding agent's Skill installer, choosing an exact reviewed release tag
or commit. The Skill is named `signetum`. Installation supplies instructions,
not a project workflow.

## Ask the agent to set up your project

For a new project:

> Use $signetum to initialize [project]. Use [our chosen tools], prepare the
> local development protocol, and show the setup changes before applying them.

For an existing repository:

> Use $signetum to inspect and adopt this repository. Preserve our tools,
> architecture and accepted decisions. Show the proposed changes first.

The agent checks prerequisites and explicitly prepares the installed Skill’s locked
execution environment.
It initializes a new project's ordinary files or inspects existing authorities,
then uses the same adoption preview. You review source, scope and changes; the
agent handles request formats and commands. Missing tools or an unavailable source
are reported with the next setup action. A source must actually be available;
an unpublished development worktree is not an installable public revision.

Host execution needs Git, Mise, Worktrunk, uv and Python 3.12+. Your application's language and test
framework stay unchanged. The agent reports and resolves required setup before
promising a usable workspace. You do not copy a template over the project.

Adoption adds the reviewed `signetum.toml` bindings. Agent entry files and application
dependencies stay unchanged. Daily commands run the installed Skill in its own environment. The upstream checkout is unnecessary; updates require a
later explicit preview. No runtime is copied into your project.

## Develop and deliver reliably

> Use $signetum to implement [behavior]. Show the intended outcome, scope and
> acceptance first. Stop at ready.

The same process supports a single Agent across sessions and parallel members.
Discuss consequential choices about behavior, architecture or delivery before
implementation.
The agent should explain the alternatives, consequences and recommendation; you
confirm the intended outcome and acceptance. It opens an isolated member workspace
and keeps significant decisions once in the change history. Ordinary command
output stays in local logs.

For parallel work, ask:

> Use $signetum to divide [change] into independent tasks. Propose ownership,
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

## Update an installed Skill

> Use $signetum to update to [exact version or commit]. Verify the new installation,
> show any required project-binding changes, then validate and deliver them.

The Skill's `update` entry displays the explicit procedure. It downloads and
changes nothing by itself. Ordinary work does not upgrade the installation.
