# Contained workspaces and one current development protocol

Status: Accepted
Review date: 2026-10-30
Supersedes: None
Superseded by: None

The owner approved the comprehensive release cleanup and implementation through
main delivery. Existing unused worktrees may be removed after inspection; valuable
state must be preserved. Tags and package publication remain outside this approval.

Protocol-created worktrees belong under the primary Git worktree's `.worktrees/`,
with an explicit per-operation destination. Caller directories and global tool
configuration cannot choose another root. Ignored managed workspace state is not
tracked delivery source; creating it does not authorize changing main's index,
tracked files or HEAD. Workspace identity is independent of its current location.
Remove unused checkouts and retire their active registration; move required
checkouts with Git, preserving dirty state. Do not introduce permanent old-path
aliases or a general migration command for this one-time repair.

Current changes use one approved change record and a significant append journal.
Preserve historical rationale and unfinished commitments while retiring the old
executable approval and ledger paths. A derived current decision set avoids both
coarse whole-document overrides and a second manually maintained summary.

Diagnostics and qualified validation share verdict semantics; only qualification
wrappers own clean-source, approval and receipt requirements. Partial test or
platform collections cannot independently judge whole-project coverage. Keep the
complete 90% requirement and conservative selection fallback. Measure execution
correctly before judging speed; retain pure matrices once and independently prove
installed and native boundaries.

Use the existing product line's next minor version, 0.3.0. Internal scaffolding
is not a separately versioned product. Keep one reusable hosted validation owner,
current architecture and task-focused Skill instructions. Revisit these choices
when demonstrated consumer or platform requirements require a different boundary,
not to preserve accidental compatibility or historical packaging layers.
