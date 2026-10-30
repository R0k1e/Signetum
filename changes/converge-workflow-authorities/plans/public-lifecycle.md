# Public lifecycle authority convergence

Status: approved
Specification: `changes/converge-workflow-authorities/specs/public-lifecycle.toml`
Base: `engine@29f1614cf57f7f3a61d10e5632bd9d552add156a`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| SELECT | FLOW-001 | Route the actual Git diff through manifest impact rules and report the deterministic selection without executing it. |
| EXECUTE | FLOW-002 | Remove the lifecycle's fixed gate and schema-v1 receipt in favor of the active manifest and exact v2 evidence. |
| STATE | FLOW-003 | Use `.git/reposeal/{validation,delivery,changes}` as the sole local-state namespace. |
| CONFORM | FLOW-004 | Protect engine and copied-runtime parity with shared black-box contract vectors. |
| VERSION | FLOW-005 | Explain engine release and Template revision as separate semantic identities. |

Implementation begins with failing public-boundary tests. It then joins the
existing selector, manifest, and evidence authorities to the eight lifecycle
operations, removes the replaced state configuration, and runs targeted plus
complete repository validation once on the clean member tip.
