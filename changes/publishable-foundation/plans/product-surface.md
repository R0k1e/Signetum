# Publishable Foundation product surface plan

Status: approved
Specification: `changes/publishable-foundation/specs/product-surface.yaml`
Base: `main@cdb92247b2367d86d60acca98c6bfc17d8daf23a`

## Preconditions

- The standalone Template decision is accepted.
- The product-surface decision is accepted.
- The Specification is human-confirmed and authorizes implementation.
- Work remains in this Plan-owned worktree until explicit batch delivery.

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| SURFACE-01 | PUBLISH-001 | Replace the package-first README with an evidence-backed product entry and bounded claims. |
| SURFACE-02 | PUBLISH-002, PUBLISH-003 | Add a Quickstart and concepts map covering one complete governed change. |
| SURFACE-03 | PUBLISH-004, PUBLISH-005 | Document Agent Team isolation, staged validation, batch assembly, delivery evidence, and acceptance. |
| SURFACE-04 | PUBLISH-006 | Document behavior-oriented unit, integration, contract, and regression testing responsibilities. |
| SURFACE-05 | PUBLISH-007 | Add customization, contribution, security, changelog, and support boundaries. |
| SURFACE-06 | PUBLISH-002, PUBLISH-003 | Add a minimal valid example change package with no alternate runtime authority. |
| SURFACE-07 | PUBLISH-008 | Add a check-only public-surface validator and positive/negative behavior tests, then bind it into the existing gate. |

## End-to-end flow

```text
evaluate README
  -> create from GitHub Template
  -> record Review clauses
  -> approve Specification and Plan
  -> open isolated member worktree(s)
  -> run targeted work and close each member with ready evidence
  -> assemble named members in one frozen batch
  -> run the complete final gate once
  -> explicitly deliver the exact validated tip
  -> human accepts or reopens delivered clauses
```

## Authority and reuse

- Lifecycle operations remain owned by `Justfile` and the delivery
  implementation; documentation links and explains them without another runner.
- Requirement relations reuse `development_foundation.traceability` for the
  active change package and teaching example.
- Current facts remain owned by `docs/ARCHITECTURE.md` and its responsibility
  pages; this change corrects their stale product identity.
- Product navigation integrity has no existing owner, so this change adds one
  pure validator and composes it into pre-commit and CI.
- README becomes the bounded public entry for product claims.

## File boundaries

Create:

```text
QUICKSTART.md
CHANGELOG.md
CONTRIBUTING.md
SECURITY.md
docs/concepts/development-lifecycle.md
docs/workflows/agent-team-delivery.md
docs/guides/customizing-the-template.md
docs/maintainers/releasing.md
examples/complete-change/**
src/development_foundation/product_surface.py
tests/unit/product_surface/test_validator.py
```

Replace or extend:

```text
README.md
docs/ARCHITECTURE.md
docs/architecture/repository-foundation.md
.pre-commit-config.yaml
.github/workflows/ci.yml
.pre-commit-config.yaml
tools/development_foundation/merge_plan_delivery.py
tests/test_batch_admission.py
```

## Behavior evidence

- A repository with every required public asset and valid local Markdown links passes.
- Removing one required guide reports that exact path.
- A local Markdown link to a missing target reports its source and target.
- HTTP links, anchors, and code samples are not mistaken for local files.
- The complete example passes the existing traceability public boundary.
- README commands are drawn from the exact eight-operation lifecycle.

## Adversarial audit

- Search public docs for upgrade, synchronization, and absolute-quality claims.
- Compare every named lifecycle operation with `Justfile`.
- Ensure the validator neither crawls outside the repository nor mutates files.
- Ensure contribution docs do not grant delivery authority implicitly.
- Ensure a document cannot satisfy the check with an untracked local file.

## Validation

```text
uv sync --locked
uv run pytest tests/unit/product_surface tests/integration/test_traceability_cli.py
uv run foundation check traceability --repository .
uv run pre-commit run --all-files
uv build
just changed cdb92247b2367d86d60acca98c6bfc17d8daf23a --explain
just ready cdb92247b2367d86d60acca98c6bfc17d8daf23a
```

The final gate runs once after explicit batch assembly, not in the member Plan.
