# Self-contained RepoSeal Template plan

Status: approved
Specification: `changes/reposeal-self-contained/specs/self-contained-template.yaml`
Base: `engine@331d297268a2f6582ea3c728193a4a50e0cc4134`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| SELF-RUNTIME | SELF-001, SELF-002 | Copy only the standard-library lifecycle runtime into the Template and bind Just recipes to it. |
| SELF-GATES | SELF-001, SELF-003 | Declare repository-owned argv validation commands and execute them without a shell. |
| SELF-SMOKE | SELF-003 | Render into a clean directory and exercise public operations without importing `reposeal`. |
| SELF-DOCS | SELF-001, SELF-002 | Replace the package-pin decision and document independent copied evolution. |

Validation uses the engine's targeted checks during work and one complete gate
on the frozen delivery batch.
