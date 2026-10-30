# Python default profile plan

Status: approved
Specification: `changes/reposeal-execution-foundation-v2/specs/python-default.toml`
Base: `engine@a5914490721f401d8dfd9330595a5eb5631b80be`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| PROFILE | EXEC-003 | Provide a declarative Python profile with configurable source, unit, and integration paths. |
| MEMBER | EXEC-003 | Contribute Ruff, ty, selected tests, secrets, and Core checks to member readiness. |
| FINAL | EXEC-003 | Contribute complete unit, integration, dependency audit, and static gates to final validation. |
| COMPOSE | EXEC-003 | Prove Python can be disabled, replaced, or combined with another synthetic language profile. |

The Template enables this profile by default. Core contains no Python-specific
branch, tool invocation, or inferred directory.
