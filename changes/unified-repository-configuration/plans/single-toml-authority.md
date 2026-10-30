# One TOML repository configuration authority

Status: approved for implementation
Specification: `changes/unified-repository-configuration/specs/single-toml-authority.toml`
Base: `engine@5cb7473644e986114930e08772cab2252de7e2df`

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| CONFIG-P1 | CONFIG-001, CONFIG-002 | Extend the strict v2 TOML model with member and final argv arrays and serialize the Template defaults once. |
| CONFIG-P2 | CONFIG-002, CONFIG-003 | Make the copied standard-library runtime read `reposeal.toml` through `tomllib` and execute the same shell-free gate boundary. |
| CONFIG-P3 | CONFIG-001, CONFIG-004 | Delete `reposeal.yaml` from the canonical Template, exact inventory, tests, documentation, and rendered `main`. |
| CONFIG-P4 | CONFIG-002, CONFIG-003, CONFIG-004 | Add public-boundary tests for a fresh render, malformed commands, missing validation, unsupported schema, and absence of fallback behavior. |

## Current authority and defect

| Concern | Current authority | Defect |
| --- | --- | --- |
| Identity, profiles, paths, impact | `reposeal.toml` and `RepositoryManifest` | Declared as sole configuration but incomplete for copied runtime execution. |
| Executable member/final commands | JSON text named `reposeal.yaml` | A second visible configuration and a misleading extension. |
| Copied runtime parsing | `template/.agents/repo-dev/runtime/lifecycle.py::_run_gate` | Reads the second JSON document directly. |
| Exact Template inventory | `src/reposeal/template.py::TOP_LEVEL` | Requires both files. |

The split contradicts the accepted language-neutral decision and the v0.2
Specification that already state `reposeal.toml` is the sole active
configuration authority. The implementation will restore one authority rather
than introduce a migration parser.

## Data flow

```text
reposeal.toml
  ├─ engine strict manifest loader
  ├─ profile / impact / evidence composition
  └─ copied tomllib runtime → member|final argv arrays → Mise exec
```

## File boundary

- Extend `src/reposeal/manifest/__init__.py` with frozen strict validation models.
- Update `template/reposeal.toml` with the current member/final commands.
- Update `template/.agents/repo-dev/runtime/lifecycle.py` to use `tomllib`.
- Delete `template/reposeal.yaml` and remove it from `TOP_LEVEL`.
- Update Template, manifest, clone-ready, documentation, and product-surface tests.
- Update architecture and customizing documentation; do not add compatibility prose.

## Through-case

A user creates a repository from RepoSeal, opens `reposeal.toml`, and sees the
Python profile, impact rules, member commands, and final commands in one file.
After `mise install` and `uv sync --locked`, `just final` parses that file with
the copied runtime and executes every argv array without a shell. Removing a
command element or adding `reposeal.yaml` causes validation to fail.

## Acceptance

```text
uv run pytest tests/unit/manifest tests/integration/test_clone_ready_template.py
just ready <approved-engine-base>
```
