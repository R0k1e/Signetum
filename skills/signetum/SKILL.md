---
name: signetum
description: Use Signetum for reliable Agent development and delivery in evolving repositories, from a single Agent across sessions to parallel coding Agents. Use to initialize a project, explicitly adopt an existing repository, or develop under this protocol; installation alone does not authorize mutation or publication.
metadata:
  version: "0.3.0"
---

# Reliable Agent development and delivery

Use the project's existing tools to keep decisions available, integrate parallel
work and explicitly deliver the exact checked source. People confirm key choices;
Agents execute and maintain concise records.

Keep cwd in the project. Invoke `sh <skill-base-dir>/scripts/signetum ...`.
The complete installed Skill owns its locked environment; no Signetum dependency
belongs in the application. Git, Mise, Worktrunk, uv and host Python 3.12+ are
prerequisites. Resolve missing tools before promising a usable workspace.
Read [adoption](references/adoption.md) for setup or updates. `update` displays
that procedure without downloading or changing files; `identity` distinguishes
complete Skill content from the project's engine pin.

Read relevant project instructions and the current decision set through
`change current` before planning. Retrieve original rationale with `change history`
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
no second handwritten decision set, execution diary or delivery report. Read
[change closure](references/change-closure.md) before declaring completion.

When behavior, ownership, commands or prerequisites change, reconcile affected
current architecture and instructions in the same change. History preserves the
reason; it does not replace current instructions. Historical approvals stay intact.
For concurrent/background/lazy paths read [stability](references/stability.md).
Read [optional validation optimization](references/validation-optimization.md)
only for requested selection, scheduling or CI partition work.

Report the furthest evidenced state: ready, integrated or delivered. Show the
generated final review before explicitly authorized delivery. Human acceptance
requires its own evidence. The maintained source is [Signetum](https://github.com/R0k1e/Signetum).
