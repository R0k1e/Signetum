# Public Template v0 uses TOML traceability

Status: Accepted
Review date: 2026-08-30
Supersedes: None
Superseded by: None

## Decision

The first promoted public Template release is `v0.1.0`. Earlier `v2.0.0` and
`v3.0.0` tags remain immutable records of pre-public architecture iterations.

Rendered repositories use TOML for Review and Specification machine contracts
and Markdown for Plans. A copied standard-library validator checks that every
Review clause has one declared disposition, every covered or deferred clause
resolves to one existing Specification, Specification ownership agrees with
the Review, and every covered clause is present in the referenced Plan.

The validator runs in both member and final gates. `main` is the default
delivery branch because it is the branch created by GitHub Template use.

## Consequences

- A fresh clone enforces requirement-accounting structure without PyPI or a
  YAML dependency.
- TOML and YAML do not coexist as public Change authorities.
- The validator proves graph closure, not requirement quality, implementation
  correctness, or test adequacy.
