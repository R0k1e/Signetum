# DevLoom product identity plan

Status: approved
Specification: `changes/devloom-brand/specs/devloom-product-identity.yaml`
Base: `main@23608f5f70bcffc98854c6366453531327235d6b`

## Outcome

Present the standalone Template as DevLoom — “Weave requirements into verified
releases” — while retaining one explicit, non-promotional machine authority for
the existing package and CLI identifiers.

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| BRAND-01 | DEVLOOM-001, DEVLOOM-002 | Replace the former public product identity across required entry points. |
| BRAND-02 | DEVLOOM-003 | Add answer-oriented positioning, category, comparison, and audience content. |
| BRAND-03 | DEVLOOM-004 | Document the public-brand/internal-protocol boundary. |
| BRAND-04 | DEVLOOM-005 | Extend the existing product-surface validator and behavior tests. |
| BRAND-05 | DEVLOOM-001, DEVLOOM-003 | Provide accurate GitHub description, topic, and release guidance for the renamed product. |

## Authority and reuse

- `README.md` remains the single public product entry.
- Existing Why, FAQ, Quickstart, workflow, and customization guides are updated;
  no duplicate documentation tree is created.
- `development_foundation.product_surface` remains the one navigation and
  required-asset validator.
- `development_foundation`, the `foundation` command, and the eight Just
  operations remain the sole machine contracts.

## File boundaries

Create:

```text
docs/product/devloom-vs-spec-tools.md
```

Update:

```text
README.md
QUICKSTART.md
docs/README.md
docs/product/why-foundation.md
docs/product/frequently-asked-questions.md
docs/concepts/development-lifecycle.md
docs/guides/customizing-the-template.md
docs/maintainers/releasing.md
CONTRIBUTING.md
SECURITY.md
CHANGELOG.md
.github/ISSUE_TEMPLATE/*.yml
pyproject.toml
src/development_foundation/product_surface.py
tests/unit/product_surface/test_validator.py
```

## Validation

```text
uv sync --locked
uv run foundation check traceability --repository .
uv build
uv run pre-commit run --all-files
just changed 23608f5f70bcffc98854c6366453531327235d6b --explain
just ready 23608f5f70bcffc98854c6366453531327235d6b
```
