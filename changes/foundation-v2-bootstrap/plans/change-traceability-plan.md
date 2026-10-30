# Requirement traceability plan

Status: approved
Specification: `changes/foundation-v2-bootstrap/specs/change-traceability.yaml`
Base: exact approved Foundation bootstrap base after repository authorities exist

## Preconditions

- The change-package ADP is accepted.
- Manifest, schema-resource loading, and CLI result contracts are available.
- No implementation begins while the Specification remains review-required.

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| TRACE-01 | FIND-003 | Implement immutable Review, clause, Spec ownership, Plan obligation, deferral, supersession, exclusion, acceptance, and reopen models. |
| TRACE-02 | FIND-003 | Implement repository inventory and reference resolution from the manifest. |
| TRACE-03 | FIND-003 | Implement complete static traceability validation. |
| TRACE-04 | FIND-005 | Implement typed evidence-provider protocol and derived state projection. |
| TRACE-05 | FIND-003, FIND-005 | Compose the checker into the sole static/final authority and expose a read-only query. |

## File operations

Create:

```text
src/development_foundation/change/**
src/development_foundation/traceability/**
src/development_foundation/status/**
schemas/review.schema.json
schemas/specification.schema.json
schemas/plan.schema.json
schemas/receipt.schema.json
tests/fixtures/changes/valid/**
tests/fixtures/changes/invalid/**
tests/unit/change/**
tests/unit/traceability/**
tests/integration/test_traceability_cli.py
```

Update:

```text
src/development_foundation/cli.py
repository-owned static gate composition
test ownership/selection manifest
```

## Contracts

- Parse external YAML into frozen typed models before relation checking.
- IDs are stable opaque values; paths are manifest-bound references.
- The inventory owner reads tracked and non-ignored untracked repository paths
  once; validators filter that inventory rather than walking independently.
- Status projection accepts typed observations for exact commits and deliveries.
- Specifications and Plans are never loaded by production applications at
  runtime; only development tooling reads them.

## Public through-case

A fixture change contains two clauses, two Specs, two Plans, exact member and
delivery observations, and human acceptance. The public CLI returns both
clauses as accepted and the parent item as accepted. Removing one Plan
obligation makes the same traversal fail before status is emitted.

## Negative fixtures

- no owner;
- duplicate owner;
- unknown clause;
- owner is draft, withdrawn, or superseded;
- Plan missing or outside its change;
- missing obligation;
- deferral target missing or not approved;
- exclusion without human authority;
- acceptance without delivery;
- reopen without prior acceptance;
- unsupported schema major;
- new file under a legacy root;
- evidence for another commit;
- malformed provider observation.

## Test classification

Retain one full CLI traversal for the valid and representative invalid change.
Place pure relation matrices in unit/property tests. Do not assert private call
order or exact prose diagnostics.

## Validation

```text
uv run pytest tests/unit/change tests/unit/traceability
uv run pytest tests/integration/test_traceability_cli.py
uv run development-foundation check traceability --repository tests/fixtures/changes/valid
uv run ruff check src/development_foundation/change src/development_foundation/traceability tests
uv run ty check
just changed <exact-base> --explain
just ready <exact-base>
```
