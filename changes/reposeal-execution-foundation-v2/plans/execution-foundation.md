# Execution foundation v2 plan

Status: approved
Specification: `changes/reposeal-execution-foundation-v2/specs/execution-foundation.toml`
Base: `engine@a5914490721f401d8dfd9330595a5eb5631b80be`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| CONFIG | EXEC-001, EXEC-002 | Replace the ambiguous YAML/JSON manifest with a strict TOML v2 authority and deterministic profile composition. |
| IMPACT | EXEC-001 | Combine declared Plan impact with Git diff impact and explain gate selection without executing validation. |
| STATES | EXEC-007 | Separate delivered evidence from human acceptance and link reopened clauses to a new Change. |
| CONTRACT | EXEC-001, EXEC-002, EXEC-007 | Preserve the eight-operation public lifecycle and reject unsupported identities without fallback. |

Behavior tests cover zero, one, and multiple profiles; namespace collisions;
explicit replacement; unexplained paths; declared/actual mismatch; and reopened
acceptance. This contract lands before dependent implementation members begin.
