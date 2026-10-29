# Repository Agent Contract

Before planning, editing or running repository commands, read
`docs/ARCHITECTURE.md` and its responsibility links, then
`.agents/repo-dev/repo.yaml`. Load mandatory policies and groups selected by
intent or paths. Report the selected groups and reasons.

Read `just protocol current` before planning. Retrieve original rationale with
`history` only when needed. While coverage is `journal_only`, consult relevant
legacy decisions; an empty working set does not withdraw accepted rules.

New work uses one `change.toml` created by `just protocol change-open <id>` in a
registered member workspace. It owns intent, requirements, acceptance, scope,
autonomy, decision proposals and necessary execution steps. Generate the
approval view with `just protocol view <record-path>`. Behavior requires actual
human confirmation; durable architecture, process and security choices require
an accepted, independently identified decision. Record confirmation accurately,
commit it before implementation and preserve unrelated work.

Use `just protocol record`, `resolve`, `retract`, `reconcile` and `retire` for
significant source events and accepted decisions. Never edit JSONL or maintain
a duplicate decision summary, execution report or review file. Preserve accepted
history. A deferral names an exact active follow-up requirement. For a changed
commitment or unauthorized irreversible action, freeze affected work and
continue independent authorized work. Legacy changes keep their declared API
until explicitly migrated; do not rewrite their accepted files.

Use the declared environment and behavioral tests. Commit significant events
before freezing the source. `ready` proves member evidence only; `final` checks
the frozen batch and generates its delivery review. Reconcile findings before
final and show the generated review before explicit delivery. Validation never
appends its own success to source. Keep the delivery worktree clean; only
explicit delivery may change it.

The lifecycle has eight operations: `workspace-open`, `changed`, `ready`,
`batch-open`, `batch-admit`, `batch-continue`, `final`, `batch-deliver`.
`protocol` and `maintenance` are separate local utilities.

Use English for repository artifacts and the user's language for discussion.
