# Batch provenance and decision numbering plan

Status: approved
Specification: `changes/reposeal-execution-foundation-v2/specs/batch-and-decisions.toml`
Base: `engine@9e0964e474df395e3222641e27bc9e27008f81f8`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| MEMBER | EXEC-005 | Record original commit, stable patch identity, ready evidence, branch, Plan, and admission commit. |
| NUMBER | EXEC-005 | Allocate formal ADP identities deterministically inside the batch and rewrite governed references. |
| DELIVERY | EXEC-005 | Invalidate numbering and final proof when the approved delivery base or batch tip changes. |

Behavior tests cover repeated and incremental admission, conflicts, concurrent
proposal numbering, reference rewriting, base movement, remote proof, and safe
cleanup retention.
