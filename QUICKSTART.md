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

The agent checks prerequisites and obtains one fixed-version Signetum setup tool.
It initializes a new project's ordinary files or inspects existing authorities,
then uses the same adoption preview. You review source, scope and changes; the
agent handles request formats and commands. Missing tools or an unavailable source
are reported with the next setup action. A source must actually be available;
an unpublished development worktree is not an installable public revision.

Host execution needs Git and Python 3.12+. Current workspace operations use the
repository-declared Mise and Worktrunk setup. Your application's language and test
framework stay unchanged. The agent reports and resolves required setup before
promising a usable workspace. You do not copy a template over the project.

After the accepted adoption is applied and committed through the existing
repository process, commands use its local runtime. The upstream checkout and
global setup engine are not daily dependencies. Updating is a later explicit
preview, not a background synchronization.

## Make a real change

> Use $signetum to implement [behavior]. Show the intended outcome, scope and
> acceptance first. Stop at ready.

The agent opens a member workspace, prepares one change record, records your
actual confirmation and implements it. Important discoveries and decisions stay
in the existing source history; ordinary command output stays in local logs.

The result names the exact commit, checks, outstanding issues and readiness.
A diagnostic retry does not clear an original failure. When you want to deliver,
request integration and full validation, then review the generated delivery
result before authorizing delivery.

The [documentation map](docs/README.md) routes configuration and operation details.
