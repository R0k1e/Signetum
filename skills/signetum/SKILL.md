---
name: signetum
description: Use Signetum for reliable Agent development and delivery in evolving repositories, from a single Agent across sessions to parallel coding Agents. Use to initialize a project, explicitly adopt an existing repository, or develop under this protocol; installation alone does not authorize mutation or publication.
metadata:
  version: "0.9.2"
---

# Reliable Agent development and delivery

Use the project's existing tools to keep decisions available, integrate parallel
work and explicitly deliver the exact checked source. People confirm key choices;
Agents execute and maintain concise records.

Keep cwd in the project. Invoke `sh <skill-base-dir>/scripts/signetum ...`.
This folder is the complete install in any agent tool; a host loads one copy.
The Skill owns a locked environment under `~/.local/share/signetum/runtime`, and
no Signetum dependency belongs in the application. Prerequisites are Git 2.7 or newer for Signetum's
own commands, Mise, Worktrunk 0.74, uv and host Python 3.12+. Cleanup through
Worktrunk needs Git 2.17. Worktrunk 0.75 or newer needs Git 2.43. Resolve
missing tools before promising a usable workspace.
Read [adoption](references/adoption.md) for setup and the one update procedure.
`update` checks the newest published release against the project and replaces
this folder in place; `update --check` is read-only. Ordinary commands other than
`update` and `install --release` stay offline. The optional guard is a host
PreToolUse hook that `install --host claude|codex` registers; when `status`
reports a `guard` entry, tell the user once how to enable it and continue.
In repositories with `signetum.toml` the guard refuses stash, destructive reset,
restore, clean and checkout, force push, unbounded `rm -rf`, direct merge or rebase, ad-hoc worktree creation or
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
one authorized change owns outcomes, scope, acceptance and execution autonomy.
Record approval once with actor, recorded_at and a neutral statement; never quote
the owner verbatim. Commit it before implementation. Record later scope changes
without re-approval; final review derives change.toml revisions from history,
starting at the first record that parses as approved. An unparsable change.toml
before that authorization stays a review diagnostic with its commit and parse
cause and is not authority. An unparsable record after authorization fails review.
`approval.date` is not a substitute for `recorded_at`.
Preserve existing authorization; installation and passing checks confer none.

Use `status` for blockers and the next action. Develop in registered isolated
worktrees. The seven delivery operations are `workspace-open`, `ready`,
`batch-open`, `batch-admit`, `batch-continue`, `final`, `batch-deliver`.
`batch-open` requires `--actor` and `--source` citing the owner authorization;
combination fixes use that recorded authority and appear in final review without
a separate change draft. Schema-1 batches keep parent-approved batch-owned records.
`ready` is the development loop: commit, run `ready`, fix, commit and rerun it
until it passes. A hook those operations install refuses an implementation commit
before the committed approval of the workspace's own change record; commit the
approval first, never bypass the hook. It also refuses added or modified Proposed
decisions and rewritten delivered commitments, including in records-only commits,
through the predicates final uses. Never hand back a member or call it done without a passing
`ready` on its current tip. `ready --explain` shows its selection without checks.
Follow [work and validation](references/worktree-validation.md) during development
and parallel coordination; use [delivery and recovery](references/delivery-recovery.md)
for integration, review, explicit delivery and cleanup. The coordinating Agent owns
scope, shared interfaces and integration; Signetum does not schedule Agents.
Every workspace ends delivered, contained (its content already reached the
delivery branch) or abandoned. Publication leaves workspaces in place and reports
cleanup as pending. `maintenance cleanup --all-delivered` removes the first two;
its sweep also recovers delivered or contained local
`change/*` and `batch/*` branches whose worktrees are already gone, subject to
non-forced Git deletion. `maintenance cleanup --branch <branch>` selects one.
Git refusals retain the branch with a diagnostic. `status` lists what each open
workspace proves. Use
`maintenance workspace-abandon`, or `branch-abandon` for a branch without a checkout,
only with the owner's actual confirmation of that tip. You may run it yourself with
`--source` citing where the owner confirmed it, such as this conversation; never infer
a confirmation. `maintenance leftovers` lists checkouts and branches created outside
Signetum that need it.

Tell the user which tests change, why, and whether evidence is removed or relaxed.
Use existing project checks. First failures remain failed after diagnostic retry.
Failure receipts retain diagnostics only, with no owed-node ledger.
Final runs every repository-selected shard to completion without failure or
unreached nodes. Scheduling, preparation, concurrency and test selection belong
to repository configuration and the operating model.
Bring a fix already in the batch into a member through
`maintenance workspace-sync --batch <batch-worktree> --message-file <path>`, not cherry-pick or a manual merge.
Every automatic commit takes the caller's message file. Follow the project's commit
convention. Where the project declares none, use one lightweight Conventional Commit
subject and do not choose `feat`, `release` or another type from the lifecycle stage.
Signetum does not add trailers or internal tags to that message. The operation record
is the proof: it is written before the Git effect and completed with the commit,
parents and tree Git stored. The same record also binds a human decision-numbering
commit: `maintenance record-decision-mapping --commit <commit> --base <approved-base>
--directory <decision-directory> --message-file <path>` requires the file to match
that commit and creates no second commit. `maintenance operation-export` and
`operation-import` move that completed proof between checkouts. Pass those public
arguments; do not read the Skill's private operation files. The same bundle imports
again unchanged. A missing, foreign, inconsistent or conflicting proof refuses.
Copied trailers do not become proof. Retained history becomes readable only after
`maintenance adopt-legacy --commit <commit>` on this checkout, including older
protocol merges and ordinary pre-protocol ancestry. That cutover does not grant
new provenance; exact reviewed old-engine text still supplies historical facts.
This checkout establishes its own cutover. Import repeats a cutover already
recorded here and refuses to establish or expand one, including on a fresh clone
or an unadopted horizon. A later merge without a structured record stays modern.
A repository-pinned batch whose checked-out engine rejects `--message-file`
refuses admission until `maintenance adopt-repository-engine --message-file <path>`
copies only the engine tree from an approved Ready commit in this repository.
That source is qualified with the same approval and ready evidence as admission.
The repository pin stays. The installed Skill and any batch that pinned an
installed engine stay unchanged. An unqualified source is refused before a
handoff object exists. Retry after a crash before the branch moves fast-forwards
the same object.
Split a large change into stacked members: `workspace-open <branch> <parent-branch>`
bases a member on another open member's tip, and its ready selects only its own diff.
After a sibling batch delivers, run `maintenance workspace-sync --message-file <path>`
in the open batch to merge the new delivery tip; members stay admitted and conflicts
use `batch-continue`.
Admission and that sync refuse two changes claiming one decision clause ID.
Ready, admission, continuation and final require approved source packages, intact
journal ancestry. Observations never block; pending observations and deferrals
appear in delivery review unfinished work. Repair an admitted defect in
a member and admit its new ready tip; never amend a commit bound by a journal.
Ready reuses passing evidence of each `inherit = true` shard that the impact
rules show no follow-up path affects, with or without a provider; a path no rule
explains reruns them all. Admission and current static or world checks remain required.
A commit that changes only change records keeps the earlier ready evidence: ready
starts no check and re-admission runs no batch gate. A batch may record, resolve or
defer findings of the changes it integrates; a deferral needs only its reason.
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

Report the furthest evidenced state: ready, integrated or delivered. Final performs
complete semantic review and emits a versioned publication binding. Delivery only
verifies that binding, exact source, local evidence and authority, and the expected
remote base; it never reparses historical journals or runs checks. Old final
receipts without that binding require a fresh final. Show the generated final
review before delivery when authorization is still missing. With explicit prior
delivery authorization, `final --deliver --target <worktree> --actor <owner>
--source <authorization> --message-file <path>` validates then publishes through the same owner.
Cleanup is a separate maintenance operation, not a publication prerequisite. Human acceptance
requires its own evidence. The maintained source is [Signetum](https://github.com/R0k1e/Signetum).

Operate consumer repositories through the installed Skill launcher, for example
`sh ~/.claude/skills/signetum/scripts/signetum <operation>`. Project wrappers
set `SIGNETUM_SKILL` and call that launcher's `scripts/signetum`; they never
call an engine in another development checkout. Update the Skill only when no
batch is open. A batch pins the opening engine; finish it with that engine or
open a new batch for the same ready members. Publishing a newer release leaves
an open batch's installed engine and pin in place. Repository self-hosting runs
batch operations from the batch worktree with its own engine. When that
checked-out engine rejects `--message-file`, adopt the qualified repository
engine in the batch before admission. The source is an approved Ready commit in
this repository, the caller message is kept, and the pin stays `repository`.
An interrupted handoff retries the recorded object.

A project that owns `core.hooksPath` should chain the machine-local Signetum
shim from its `reference-transaction` hook:

```sh
input=$(cat)
shim="$(git rev-parse --git-common-dir)/signetum/hooks/reference-transaction"
if [ -x "$shim" ]; then printf '%s\n' "$input" | "$shim" "$@" || exit $?; fi
```

Preparation verifies the effective chain with a real Git probe. Check status for
`commit_check.status`: an inactive check warns with its cause and chaining
snippet; ready and final still judge immutable commit attribution.
