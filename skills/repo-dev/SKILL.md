---
name: repo-dev
description: Use a repository's reliable agentic development and delivery protocol to plan changes, retain decisions, validate implementation, or prepare delivery. Use for explicit adoption or repositories that declare this protocol; installation alone does not authorize mutation or publication.
metadata:
  version: "4.0.0"
---

# Reliable agentic development and delivery

Read the repository's Agent contract, architecture entry and declared development
manifest. Load mandatory policies and only the groups selected by intent or
paths; report those groups and reasons. Repository bindings own paths,
environments, runners and delivery targets. If adoption or a required binding
is absent, report what is missing before mutation. Do not install a workflow
into an existing repository merely because this skill was invoked.

Keep cwd in the user's repository. The local utility launcher is
`sh <skill-base-dir>/scripts/repo-dev <command> [arguments]`; it delegates to
the adopted `.agents/repo-dev/run protocol`, or the existing `just protocol`
binding. `adopt` delegates to an installed reviewed engine before local adoption.
It does not download or update anything.
Honor declared schema, profile and skill identities. A mismatch requires an
explicit adoption change; installing this folder does not change existing pins.
Use the repository's declared lifecycle commands for workspace and delivery
operations. Read [adoption](references/adoption.md) only when setting up or
migrating a repository.

Before planning, read the current decision working set with `current`. Retrieve
original rationale with `history --event <id>` or `history --change <id>` only
when relevant. The view also lists historical authority sources and their declared standing.
Consult relevant retained sources; `journal_only` does not mean they were migrated.
For new or changed behavior, read
[change approval](references/spec-plan-decisions.md); create one change record
and generate its approval view. Read [change closure](references/change-closure.md)
for scope, deferral or completion checks.

For changes introducing concurrency, background work or lazy initialization, read
[stability](references/stability.md).

During implementation, read [work and validation](references/worktree-validation.md).
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
