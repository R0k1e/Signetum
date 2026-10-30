# A gate states what it checked

Status: approved
Specification: `changes/gates-and-citations-state-what-they-check/specs/stated-checks.toml`
Base: `engine@9bbfde9f84f15f51293f9399bade8b6ce1b4ed0e`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| CITE | STATE-001, STATE-002 | Load decision content at the loading boundary and validate fulfilment and reciprocal supersession. |
| REPAIR | STATE-002 | Write the reciprocal entry at delivery and repair the one already broken. |
| BOUND | STATE-003 | Declare and enforce a shard time bound with its own reported outcome. |
| EXCLUDE | STATE-004 | Hold an exclusive batch lock across admission and continuation. |
| STATE | STATE-005 | Document the re-admission recovery path with the operations. |
| FRESH | STATE-006 | Protect the environment-shard dependency with a regression. |

CITE precedes REPAIR: the repair is only verifiable once the gate can observe
it. The others are independent.

Gate scope, the remaining finding from the same review, is deliberately out of
scope here. Every shard command in this repository is still whole-tree, so
narrowing them is its own change rather than a sixth concern in this one.
