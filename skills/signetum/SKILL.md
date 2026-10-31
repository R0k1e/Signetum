---
name: signetum
description: Use Signetum for reliable Agent development and delivery in evolving repositories, from a single Agent across sessions to parallel coding Agents. Use to initialize a project, explicitly adopt an existing repository, or develop under this protocol; installation alone does not authorize mutation or publication.
metadata:
  version: "0.3.0"
---

# Reliable Agent development and delivery

Keep consequential decisions available across sessions, validate integrated work
and deliver only the reviewed checked source. People make key choices; Agents
perform routine execution and maintain concise records.

Honor the project's existing instructions and environment authority. Inspect
`signetum.toml` for command, input, record and delivery bindings. Architecture and
Agent entry files are project-owned context, not installation prerequisites.
Read relevant existing policies without adding a new policy router.

Keep cwd in the user's repository. Run
`sh <skill-base-dir>/scripts/signetum <operation> [arguments]`.
One explicit `setup` prepares this Skill's locked isolated engine environment;
ordinary operations never install, repair or update it. Git, Mise, Worktrunk,
uv and host Python 3.12+ are prerequisites. Application preparation runs only
through the project's declared commands and environment.
Read [adoption](references/adoption.md) for first use or an explicit update.
A missing or mismatched project engine pin requires a reviewed adoption change,
not automatic replacement. The same launcher serves the eight lifecycle
operations and the record/status/maintenance utilities.

Use `status` to see workspace state, retained findings, source-bound receipts and
the next action. It executes no checks and does not grant readiness. Before
planning, read the current decision working set with `current`. Retrieve
original rationale with `history --event <id>` or `history --change <id>` only
when relevant. Historical authorities are read on demand from the declared decision directory;
retrieve relevant original rationale rather than loading the complete archive.
For new or changed behavior, read
[change approval](references/spec-plan-decisions.md); create one change record
and generate its approval view. Read [change closure](references/change-closure.md)
for scope, deferral or completion checks.

For parallel development, follow the coordination guidance in
[work and validation](references/worktree-validation.md). The coordinating Agent
owns task scope, dependencies and named integration; Signetum does not schedule
Agents or impose a global host allocation.

For changes introducing concurrency, background work or lazy initialization, read
[stability](references/stability.md).

During implementation, read [work and validation](references/worktree-validation.md).
Tell the user when tests change, why, and whether the evidence is reduced.
Trace affected architecture, commands and usage instructions when a behavior,
owner or prerequisite changes. Update those current authorities in the same
change; history is the reason, not a substitute for current instructions.
Keep significant findings and accepted decision edits in the source journal
through its tools. Do not maintain a second handwritten decision summary,
execution report, review document or command-by-command log.

For integration, final review, delivery or recovery, read
[delivery and recovery](references/delivery-recovery.md). A passed check proves
its observed source; it grants no permission for a later operation. Report only
the furthest evidenced state: ready, integrated or delivered. Human acceptance
requires its own explicit evidence.

The maintained implementation and extension point is
[Signetum](https://github.com/R0k1e/Signetum). Adopt a later revision as an explicit
local change; never replace repository authorities automatically.
