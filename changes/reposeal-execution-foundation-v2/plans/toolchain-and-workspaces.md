# Mise and Worktrunk runtime plan

Status: approved
Specification: `changes/reposeal-execution-foundation-v2/specs/toolchain-and-workspaces.toml`
Base: `engine@a5914490721f401d8dfd9330595a5eb5631b80be`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| MISE | EXEC-006 | Validate and invoke pinned external tools through Mise while language ecosystems own locked dependencies. |
| WORKTREE | EXEC-006 | Project workspace creation, discovery, and removal through Worktrunk only. |
| SELF-CONTAINED | EXEC-006 | Keep the copied runtime standard-library based and independent of the RepoSeal distribution. |

Behavior tests exercise missing tools, invalid Worktrunk output, registered
workspace identity, non-interactive invocation, and retained dirty or advanced
worktrees.
