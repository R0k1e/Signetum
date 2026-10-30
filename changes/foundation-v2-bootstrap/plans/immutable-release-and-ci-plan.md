# Immutable release and check-only CI plan

Status: approved
Specification: `changes/foundation-v2-bootstrap/specs/immutable-release-and-ci.yaml`
Base: exact approved Foundation bootstrap base after final-evidence authority exists

## Preconditions

- Foundation package, schema bundle, and repo-dev skill build locally.
- The repository has one exact-commit final receipt authority.
- Remote publication remains separately authorized.

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| RELEASE-01 | FIND-008 | Replace branch-mutating CI with exact-SHA check-only jobs. |
| RELEASE-02 | FIND-006 | Build package, schema, skill, compatibility metadata, and checksums as one release set. |
| RELEASE-03 | FIND-006 | Verify exact final evidence before publication. |
| RELEASE-04 | FIND-007 | Define immutable downstream selection and refusal of moving identities. |
| RELEASE-05 | FIND-006, FIND-007 | Publish v2 only after explicit authorization and confirm remote artifact identity. |

## File operations

Replace:

```text
.github/workflows/ci.yml
.github/workflows/cd.yml
```

Create or update:

```text
.github/workflows/release.yml
src/development_foundation/release/**
src/development_foundation/receipts/**
schemas/release-metadata.schema.json
tests/unit/release/**
tests/unit/tooling/test_ci_authority.py
tests/integration/test_release_artifacts.py
```

Delete:

- auto-fix job;
- auto-merge job;
- branch deletion;
- write permissions from ordinary validation;
- conditional successful publication skip;
- unpinned moving tool/action versions where immutable pins are supported.

## Exact-tree contract

Every test and check receives the same source SHA. A formatter may report a
failure but cannot change the tree. Final evidence binds source, working tree,
lock, schemas, profiles, skill, gate, and result. Release verifies that evidence
against the tag commit before building or publishing.

## Release set

```text
development_foundation-<version>.whl
development_foundation-<version>.tar.gz
repo-dev-<version>.artifact
schemas-<version>.artifact
compatibility.json
SHA256SUMS
```

## Failure cases

- tag commit differs from final evidence;
- source or lock is dirty;
- one artifact version differs;
- digest mismatch;
- unsupported schema declaration;
- missing requested publication credential;
- remote already contains a conflicting immutable identity;
- workflow checks out a branch head;
- validation job has contents-write permission.

## Validation

```text
uv run pytest tests/unit/release tests/unit/tooling/test_ci_authority.py
uv run pytest tests/integration/test_release_artifacts.py
uv run development-foundation release preflight --source <exact-sha>
uv build
just changed <exact-base> --explain
just ready <exact-base>
```

Tagging, pushing, repository renaming, and publishing are deliberately absent
from member validation and require explicit authorization after final.
