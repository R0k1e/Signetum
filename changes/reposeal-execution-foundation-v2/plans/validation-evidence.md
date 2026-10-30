# Validation graph and evidence v2 plan

Status: approved
Specification: `changes/reposeal-execution-foundation-v2/specs/validation-evidence.toml`
Base: `engine@a5914490721f401d8dfd9330595a5eb5631b80be`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| GRAPH | EXEC-004 | Resolve named member/final gates and required shards from Core, profiles, and repository additions. |
| RECEIPT | EXEC-004 | Bind receipts to code, configuration, profiles, graph, lockfiles, tools, and executed work. |
| COMBINE | EXEC-004 | Combine only complete shard evidence for one exact identity. |

Behavior tests reject stale, incomplete, cross-commit, cross-configuration, and
cross-toolchain evidence through public validation operations.
