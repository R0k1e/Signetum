# Development lifecycle

Open a registered member workspace with `just workspace-open <branch> <base>`.
Inside it, `just protocol current` reads the current decision working set and
`just change-open <id>` creates one unapproved `change.toml`. Fill the intent,
requirements, acceptance, exclusions, transfers, autonomy and execution steps.
`just protocol view <record-path>` generates the approval proposal. Record the
owner's actual confirmation and exact contract digest before implementation.

Keep significant findings and accepted clause edits in `events.jsonl` through
`just protocol` journal commands. Original rationale is available through
`history`; the current decision view is derived rather than maintained twice.
`status` shows findings and their standing answers. Ordinary operations use
semantic fields, for example `just protocol record --id finding --requirement
REQ-001 --summary "What was found" --reason "Why it matters"`. The tool binds
the approved change and history; use `--change` only if the workspace is ambiguous.
`current` also lists committed historical decision sources and their standing. Preserve historical
accepted documents until an explicit reviewed migration replaces their authority.

Run the existing repository checks during implementation. A failed diagnostic
retry remains a failure; fix it and run ordinary validation again. `ready`
qualifies the exact member tip. Named members enter a batch through `batch-open`
or `batch-admit`; `batch-continue` recovers an open merge. `final` validates the
frozen batch and generates the delivery review, refusing pending discoveries,
unrecorded approved decisions or unavailable effective evidence. Validation
does not append success to source. Present that review before explicit
`batch-deliver`; readiness alone authorizes neither integration nor publication.

Use `just maintenance worktree-prepare <path>` after dependency inputs change.
Preparation and `changed` do not grant readiness. Ordinary command output stays
in local logs and receipts; do not create duplicate execution or review reports.
