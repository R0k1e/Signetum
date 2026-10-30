# Repository Agent Contract

Before planning, editing, or running repository commands, read
`docs/ARCHITECTURE.md`, `.agents/signetum/repo.yaml`, and every policy selected
by task intent or affected paths. Report the selected policy groups and reasons
before repository operations.

Use `uv` for Python commands. Keep active work in a change-owned worktree.
Validation is check-only; delivery requires an explicit request. Never use
stash, destructive reset/restore/clean, force push, direct merge, or ad-hoc
worktree deletion. Preserve unrelated changes and keep credentials, caches,
receipts, and local paths out of Git.

Approved change contracts own outcomes; execution steps cannot narrow them. Accepted decisions
must precede architecture, process, or security changes. Keep their basis once
in the owning change; standalone ADRs are conditional cross-change authorities.
Ordinary implementation and command output create no extra decision document. Use English for code
and technical documents. Use Chinese for user discussion.

For new work, use `just protocol current` for the decision working set, then
`just protocol change-open <id>` in the registered member workspace. Maintain
one `change.toml` and its significant source journal; use `just protocol view`
for approval and `history` for rationale on demand. Record, resolve, retract,
reconcile and retire through `just protocol`, never direct JSONL edits. Do not
write duplicate execution or decision summaries. Until reviewed legacy adoption
is complete, `journal_only` coverage requires relevant historical authorities;
existing legacy changes retain their declared deviation API and accepted files.
