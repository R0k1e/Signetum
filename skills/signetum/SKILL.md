---
name: signetum
description: Use Signetum for reliable Agent development and delivery in evolving repositories, from a single Agent across sessions to parallel coding Agents. Use to initialize a project, explicitly adopt an existing repository, or develop under this protocol; installation alone does not authorize mutation or publication.
metadata:
  version: "0.3.1"
---

# Reliable Agent development and delivery

Use the project's existing tools to keep decisions available, integrate parallel
work and explicitly deliver the exact checked source. People confirm key choices;
Agents execute and maintain concise records.

Keep cwd in the project. Invoke `sh <skill-base-dir>/scripts/signetum ...`.
The complete installed Skill owns its locked environment; no Signetum dependency
belongs in the application. Prerequisites are Git 2.7 or newer for Signetum's
own commands, Mise, Worktrunk 0.74, uv and host Python 3.12+. Cleanup through
Worktrunk needs Git 2.17. Worktrunk 0.75 or newer needs Git 2.43. Resolve
missing tools before promising a usable workspace.
Read [adoption](references/adoption.md) for setup and the one update procedure.
Bare `update` installs the latest stable release and prepares that Skill.
`update --check` and `update --to` are optional. Ordinary commands other than
`update` stay offline.
`identity` reports complete Skill and actual engine identities; projects declare
configuration/protocol compatibility, not an implementation pin.

For development planning, read relevant project instructions and the current
decision set through `change current`. Questions and read-only reviews load only
relevant context; do not open a change or run delivery for them. Retrieve original
rationale with `change history`
only when needed. For new or changed behavior, follow [change approval](references/spec-plan-decisions.md):
one approved change owns outcomes, scope, acceptance and execution autonomy.
Preserve existing authorization; installation and passing checks confer none.

Use `status` for blockers and the next action. Develop in registered isolated
worktrees. The eight delivery operations are `workspace-open`, `changed`, `ready`,
`batch-open`, `batch-admit`, `batch-continue`, `final`, `batch-deliver`.
Follow [work and validation](references/worktree-validation.md) during development
and parallel coordination; use [delivery and recovery](references/delivery-recovery.md)
for integration, review, explicit delivery and cleanup. The coordinating Agent owns
scope, shared interfaces and integration; Signetum does not schedule Agents.

Tell the user which tests change, why, and whether evidence is removed or relaxed.
Use existing project checks. First failures remain failed after diagnostic retry.
Record consequential discoveries and their reasons through `change record/resolve`;
current decisions are derived. Ordinary command output stays in local logs. Keep
no second handwritten decision set, execution diary or delivery report. Use the
closure section of [change approval](references/spec-plan-decisions.md)
when closing an owned change.

When behavior, ownership, commands or prerequisites change, reconcile affected
current architecture and instructions in the same change. History preserves the
reason; it does not replace current instructions. Historical approvals stay intact.
For concurrent/background/lazy paths read [stability](references/stability.md).
Read [optional validation optimization](references/validation-optimization.md)
only for requested selection, scheduling or CI partition work.

Report the furthest evidenced state: ready, integrated or delivered. Show the
generated final review before explicitly authorized delivery. Human acceptance
requires its own evidence. The maintained source is [Signetum](https://github.com/R0k1e/Signetum).
