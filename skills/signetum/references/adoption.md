# Set up a new or existing repository

Use this procedure when setup or an explicit upgrade is requested. Skill
installation alone does not authorize repository mutation. Keep cwd in the
user's project; obtain tooling separately rather than copying an upstream tree.

## Acquire the setup tool once

Inspect Git, host Python 3.12+ and uv, plus the project's declared Mise/Worktrunk
workspace setup. Report missing prerequisites and the needed action; do not
silently trust or replace configuration. Choose an exact reviewed available
release artifact or source commit. The agent constructs the literal command:

```sh
uv tool install /path/to/signetum-<version>-py3-none-any.whl
# Source fallback; replace the placeholder with the reviewed available commit.
uv tool install 'git+https://github.com/R0k1e/Signetum.git@<commit>'
```

Use one of these routes, not both. The Skill launcher routes `adopt` to that
installed tool. It does not fetch tooling itself. A missing release or source is
a setup refusal, not permission to substitute an old RepoSeal package or latest
unreviewed code. Upgrades use the same preview against current local files.

## Prepare the project and review adoption

For a new project, initialize the selected application's ordinary files and Git
history. Establish its actual architecture, tools and test command. Do not create
placeholder product facts just to satisfy adoption. For an existing project,
inspect and preserve its authorities, metadata, locks and accepted decisions.
Both cases now use the same path:

1. Run `adopt inspect` if an inventory helps; preview also checks its bindings.
2. Prepare the request using the [binding contract](https://github.com/R0k1e/Signetum/blob/main/docs/guides/existing-runners.md).
3. Run `adopt preview`, show exact file and binding changes, and resolve missing
   prerequisites. The user reviews the preview, not protocol syntax.
4. Apply only the approved plan digest. Changed source, files or runtime require
   a fresh preview. Inspect interruption before retrying; do not overwrite drift.
5. Commit accepted setup using the project's existing process. Verify its actual
   local command and complete a small authorized change through ready.

Adoption executes no application commands and creates no development approval or
readiness. Application tests and preparation stay explicitly owned by the project.

## Continue locally

The launcher uses `.agents/signetum/run protocol`, or an existing `just protocol`
binding. Workspace and delivery use the repository's local lifecycle commands.
No upstream clone, engine install or remote ledger is needed for daily work.

Read relevant retained decisions before new work. Let the agent organize original
sources and propose only consequential current decisions through the ordinary
change process. Preserve evidence and rationale; source organization does not
grant approval or require a dedicated migration command.
