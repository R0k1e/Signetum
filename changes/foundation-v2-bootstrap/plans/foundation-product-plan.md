# Versioned foundation product plan

Status: approved
Specification: `changes/foundation-v2-bootstrap/specs/foundation-product.yaml`
Base: `origin/main@7a789bfe21221ef2ff67f2ed0a4863933ab0b83f`

## Preconditions

- Both foundation ADPs are accepted.
- The Specification is human-confirmed and `implementation_authorized` is true.
- WP1 establishes repository-owned validation commands before later commits.

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| PRODUCT-01 | FIND-001, FIND-012 | Establish AGENTS, Architecture, manifest, change, validation, and delivery authorities. |
| PRODUCT-02 | FIND-001, FIND-002 | Replace the placeholder application with the `development_foundation` package and CLI. |
| PRODUCT-03 | FIND-002, FIND-009 | Implement manifest-selected profiles and downstream adapter protocols. |
| PRODUCT-04 | FIND-001 | Delete the superseded template application and initializer. |
| PRODUCT-05 | FIND-012 | Prove active Plan isolation and delivered Plan provenance. |

## End-to-end flow

```text
foundation CLI
  -> load immutable packaged schemas
  -> parse repository manifest
  -> validate selected profile identities
  -> compose generic check with repository adapters
  -> emit one JSON result
```

## File operations

Create:

```text
AGENTS.md
docs/ARCHITECTURE.md
docs/architecture/repository-foundation.md
docs/architecture/validation-and-delivery.md
.agents/repo-dev/repo.yaml
.agents/repo-dev/references/**
src/development_foundation/__init__.py
src/development_foundation/cli.py
src/development_foundation/manifest/**
src/development_foundation/profiles/**
src/development_foundation/evidence/**
schemas/**
profiles/**
Justfile
mise.toml
tests/unit/**
tests/integration/**
```

Replace:

```text
README.md
pyproject.toml
.pre-commit-config.yaml
```

Delete only after replacement public tests pass:

```text
CLAUDE.md
main.py
config/**
src/placeholder_name/**
scripts/init_repo.sh
tests/test_cli.py
tests/test_config.py
tests/test_core.py
tests/test_smoke.py
```

## Reuse judgment

- Reuse uv/hatch packaging mechanics, but rename the distribution and package.
- Retain useful Python quality configuration in `profiles/python-uv`.
- Do not retain a placeholder-generation compatibility command.
- Define profile composition through typed declarations, not directory scanning
  or implicit auto-registration.

## Behavior tests

- CLI validates a complete fixture manifest through its public command.
- Unsupported manifest/profile/schema identities fail through the same command.
- Package-resource tests inspect the built wheel, not only the source tree.
- A repository adapter fixture proves downstream facts never enter the generic
  package.
- A lifecycle fixture proves the Plan is absent from the delivery branch before
  delivery and present with implementation provenance afterward.

## Adversarial checks

- Search built package contents for PyLM paths and product identifiers.
- Reject absolute paths and moving foundation identities.
- Reject two profile declarations claiming the same authority.
- Reject an undeclared profile dependency.
- Verify deleting the legacy initializer leaves no alias or redirect.

## Validation

Target commands after PRODUCT-01 binds them:

```text
uv sync --locked
uv run pytest tests/unit/manifest tests/unit/profiles tests/integration/test_cli_manifest.py
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
uv run pytest tests/integration/test_built_distribution.py
just changed <exact-base> --explain
just ready <exact-base>
```

The final gate is not run by this member Plan.
