# A tree which hosts no Change carries no Change identity

Status: approved
Specification: `changes/a-tree-without-changes-carries-none/specs/no-change-identity.toml`
Base: `engine@f0e685ec6e4bb508a3ccce38fd367a995541914b`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| DETECT | CARRY-001 | Decide from the manifest's declared specification authority whether a tree hosts a Change. |
| ADMIT | CARRY-001, CARRY-002 | Require a Plan trailer only where a Change can exist. |
| RECONCILE | CARRY-001 | Reconcile no Change identity for such a tree, explicitly. |
| MIRROR | CARRY-001, CARRY-002 | Apply the same contract to the Template runtime. |

DETECT precedes the rest. The plan-shape rule is untouched throughout.
