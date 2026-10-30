# A declared authority runs in a gate

Status: approved
Specification: `changes/traceability-joins-the-gate/specs/authority-in-the-gate.toml`
Base: `engine@e411f2f904c77290f02b9b902a9bfe3ec47b1ce3`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| COMPLETE | GATE-002 | Name the delivery the existing acceptance record already had. |
| RUN | GATE-001 | Declare the authority as a shard in both gates. |
| PROTECT | GATE-001 | Prove by regression that both gates carry it. |

COMPLETE precedes RUN: the gate cannot be green until the record it judges is.
