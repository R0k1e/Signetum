---
name: signetum
description: Use Signetum for reliable Agent development and delivery in evolving repositories, from a single Agent across sessions to parallel coding Agents. Use to initialize a project, explicitly adopt an existing repository, or develop under this protocol; installation alone does not authorize mutation or publication.
metadata:
  version: "0.3.3"
---

# Reliable Agent development and delivery

Use the project's existing tools to keep decisions available, integrate parallel
work and explicitly deliver the exact checked source. People confirm key choices;
Agents execute and maintain concise records.

Keep cwd in the project. Invoke `sh <skill-base-dir>/scripts/signetum ...`.
In Claude Code and Codex the `signetum` plugin installs this Skill and its
command guard; do not also install the plain Skill there. Other agent tools use
this folder as a plain Skill, without the guard. The Skill owns a locked
environment under `~/.local/share/signetum/runtime`, and no Signetum
dependency belongs in the application. Prerequisites are Git 2.7 or newer for Signetum's
own commands, Mise, Worktrunk 0.74, uv and host Python 3.12+. Cleanup through
Worktrunk needs Git 2.17. Worktrunk 0.75 or newer needs Git 2.43. Resolve
missing tools before promising a usable workspace.
Read [adoption](references/adoption.md) for setup and the one update procedure.
`update` checks the latest pinned release against the project, then upgrades
each host through its plugin manager, or replaces a plain Skill folder in place;
`update --check` is read-only. Ordinary commands other than `update` stay offline.
The guard refuses stash, destructive reset, restore, clean and checkout, force
push, unbounded `rm -rf`, direct merge or rebase, ad-hoc worktree creation or
removal, `branch -D` and pre-commit on a dirty tree. Use the operation its
refusal names; do not work around it. Without the guard, follow the same rules:
the protocol guarantees still come from receipts and from `batch-deliver` being
the only operation that advances the delivery branch; the guard only refuses
work-losing commands early.
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
worktrees. The seven delivery operations are `workspace-open`, `ready`,
`batch-open`, `batch-admit`, `batch-continue`, `final`, `batch-deliver`.
`ready` is the development loop: commit, run `ready`, fix, commit and rerun it
until it passes. Never hand back a member or call it done without a passing
`ready` on its current tip. `ready --explain` shows its selection without checks.
Follow [work and validation](references/worktree-validation.md) during development
and parallel coordination; use [delivery and recovery](references/delivery-recovery.md)
for integration, review, explicit delivery and cleanup. The coordinating Agent owns
scope, shared interfaces and integration; Signetum does not schedule Agents.
Every workspace ends delivered, contained (its content already reached the
delivery branch) or abandoned. Delivery and `maintenance cleanup --all-delivered`
remove the first two; `status` lists what each open workspace proves. Use
`maintenance workspace-abandon` only with the owner's actual confirmation of that tip.

Tell the user which tests change, why, and whether evidence is removed or relaxed.
Use existing project checks. First failures remain failed after diagnostic retry.
Recording a failed test as outside the change's scope does not offset that failure.
Bring a fix already in the batch into a member through
`maintenance workspace-sync --batch <batch-worktree>`, not cherry-pick or a manual merge.
Split a large change into stacked members: `workspace-open <branch> <parent-branch>`
bases a member on another open member's tip, and its ready selects only its own diff.
After a sibling batch delivers, run `maintenance workspace-sync` in the open batch to
merge the new delivery tip; members stay admitted and conflicts use `batch-continue`.
Admission and that sync refuse two changes claiming one decision clause ID.
Ready, admission, continuation and final require approved source packages, intact
journal ancestry and resolved source observations. Repair an admitted defect in
a member and admit its new ready tip; never amend a commit bound by a journal.
Ready reuses passing evidence of each `inherit = true` shard that the impact
rules show no follow-up path affects, with or without a provider; a path no rule
explains reruns them all. Admission and current static or world checks remain required.
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
