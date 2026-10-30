# Public v0 traceability plan

Status: approved
Specification: `changes/reposeal-v0-traceability/specs/template-traceability.yaml`
Base: `engine@430e4689527abcfe4da5074536a3a8f0c10b45fd`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| FORMAT | V0-002 | Replace public YAML Review/Spec artifacts with TOML and remove the old paths. |
| VALIDATOR | V0-003 | Add a standard-library validator for clause ownership, referenced Specs, Plans, and deferrals. |
| GATE | V0-003 | Run traceability in member, final, and GitHub CI paths. |
| DELIVERY | V0-004 | Declare main as the one default delivery branch. |
| RELEASE | V0-001 | After exact main delivery, create v0.1.0 without moving historical tags. |
| EVIDENCE | V0-002, V0-003 | Cover valid and adversarial clean-room behavior through copied public scripts. |
