# Example greeting plan

Status: approved
Specification: `examples/complete-change/specs/greeting.toml`
Base: `origin/main@example-base-commit`

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| EXAMPLE-PLAN-01 | EXAMPLE-001 | Add the greeting through its public command and cover valid and invalid behavior. |

## Evidence

- The public command returns the exact greeting for a valid display name.
- The same boundary rejects an empty display name.
- No test asserts a private helper or internal call order.
