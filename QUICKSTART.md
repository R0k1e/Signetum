# First use

Start with one repository and one small real change. You need Git, a coding
agent with the standard `repo-dev` Skill, and a host Python 3.12 or later.
Workspace operations also use the repository's reviewed Mise and Worktrunk setup.
Your application's language, package manager and test framework stay the same.

## Install the Skill

Install the `skills/repo-dev` folder from the Signetum engine revision you want
to use with your agent's standard skill installer. Ask:

> Use repo-dev to inspect this repository. Show what is needed for adoption;
> do not change the project yet.

For an existing repository, the agent needs the Signetum engine once to prepare
its local runtime. Install a reviewed wheel with
`uv tool install /path/to/signetum-<version>-py3-none-any.whl`, or install an exact
reviewed source revision with
`uv tool install 'git+https://github.com/R0k1e/Signetum.git@<reviewed-commit>'`.
Replace the placeholders with the artifact or exact commit you reviewed.
The resulting `signetum adopt` command prepares local files; normal development
then uses those repository-owned files, without an installed engine dependency.

For a new repository, use GitHub's **Use this template**, clone it and fill in its
actual product and architecture facts. Inspect `mise.toml`, run `mise trust
mise.toml`, `mise install` and `uv sync --locked`. The Template already carries
its runtime and commands; it does not need the existing-repository installer.

## Review adoption once

Ask the agent to preserve existing instructions, architecture, test commands,
lockfiles and delivery settings. It prepares a preview showing exact file
changes and missing prerequisites. Follow the [adoption guide](docs/guides/existing-runners.md)
when inspecting those bindings. Confirm the preview when it matches your project.
Applying it does not approve a development task, run project commands, or deliver
anything. If a target changed, obtain a fresh preview rather than overwrite it.

## Make one change

> Use repo-dev to implement [one small behavior]. Show me the intended outcome,
> scope and how you will verify it before implementation. Stop at ready.

The agent opens an isolated workspace, writes one change record and shows its
approval view. You check the behavior and boundaries. The agent records your
confirmation, implements the change and runs the repository checks.
Significant discoveries go into its journal; routine command output stays in logs.
The agent reads current decisions and relevant original sources before deciding
again. You do not maintain a second decision summary or execution report.

## Check the result

A useful result names what changed, the checks run, unresolved issues and the
exact commit that passed `ready`. A failed test remains a failure after a narrow
diagnostic retry; the source needs repair and fresh ordinary validation.

When you want to ship, explicitly request batch integration and full validation.
Inspect the generated delivery review before authorizing delivery. The
[delivery guide](docs/workflows/agent-team-delivery.md) covers that separate step.
Installation, readiness and delivery are distinct outcomes.
