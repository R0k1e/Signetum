# Repository Agent Contract

Before planning, editing, or running repository commands:

1. Read `docs/ARCHITECTURE.md` and its linked responsibility documents.
2. Read `.agents/repo-dev/repo.yaml`.
3. Load every mandatory policy and every policy selected by intent or path.
4. Emit a bounded routing manifest with each selected group and its reason.

Behavior changes require a human-confirmed specification. Architecture,
process, and security decisions require an accepted standalone decision.
Develop in a plan-owned worktree; keep the delivery worktree clean. Preserve
unrelated changes. Use the repository-declared environment authority and
behavioral tests. Never hide a deferred requirement in prose: point it to an
active specification. Delivery is explicit and is the only operation allowed
to mutate the delivery worktree.

The public lifecycle has exactly eight operations:

```text
workspace-open <branch> <base>
changed <base> [--explain]
ready <base>
batch-open --member <worktree-path> [--member <worktree-path> ...]
batch-admit <batch> --member <worktree-path> [--member <worktree-path> ...]
batch-continue <batch>
final
batch-deliver <source> <target> <expected-base> <expected-batch-tip>
```

Use English for repository artifacts and the user's language for discussion.
