# Repository Agent Contract

Before planning, editing, or running repository commands, read
`docs/ARCHITECTURE.md`, `.agents/repo-dev/repo.yaml`, and every policy selected
by task intent or affected paths. Report the selected policy groups and reasons
before repository operations.

Use `uv` for Python commands. Keep active work in a plan-owned worktree.
Validation is check-only; delivery requires an explicit request. Never use
stash, destructive reset/restore/clean, force push, direct merge, or ad-hoc
worktree deletion. Preserve unrelated changes and keep credentials, caches,
receipts, and local paths out of Git.

Specifications own behavior, and Plans cannot narrow them. Accepted decisions
must precede architecture, process, or security changes. Use English for code
and technical documents. Use Chinese for user discussion.
