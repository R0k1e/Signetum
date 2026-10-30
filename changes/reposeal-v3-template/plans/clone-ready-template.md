# RepoSeal v3 clone-ready Template plan

Status: approved
Specification: `changes/reposeal-v3-template/specs/clone-ready-template.yaml`
Base: `main@d331ef4dbf830a1267859f055f3b483c77b1c87f`

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| V3-ENGINE | V3-002, V3-007 | Rename the package and CLI to `reposeal`, keeping engine source and governance on the source branch. |
| V3-TEMPLATE | V3-001, V3-003, V3-005 | Add one minimal Template source that reserves no application root and carries no maintainer residue. |
| V3-LANGUAGE | V3-004 | Add equivalent English and Simplified Chinese adoption entry points. |
| V3-RENDER | V3-006 | Add deterministic render, inventory, and drift validation for the default-branch artifact. |
| V3-SMOKE | V3-001, V3-006, V3-007 | Validate a fresh rendered repository through its public lifecycle boundary. |

## End-to-end release flow

```text
engine change -> ready -> frozen engine batch -> final -> deliver engine
  -> publish exact reposeal package -> verify artifact
  -> render engine/template -> clean-room validation
  -> publish rendered tree to main -> confirm GitHub Template
```

## File boundaries

Engine rename or extend:

```text
src/reposeal/**
tools/reposeal/**
tests/**
schemas/**
profiles/**
skills/**
pyproject.toml
uv.lock
```

Create:

```text
template/**
src/reposeal/template.py
tests/integration/test_clone_ready_template.py
docs/decisions/ADP-reposeal-engine-and-template-are-separate-branches.md
```

Remove from the rendered Template:

```text
.claude .vscode src tests tools schemas skills profiles pyproject.toml uv.lock
RepoSeal maintainer changes, decisions, audits, and release workflow
```

## Validation

```text
uv sync --locked
uv build
uv run pre-commit run --all-files
uv run reposeal template check --source template
uv run pytest tests/integration/test_clone_ready_template.py
just changed d331ef4dbf830a1267859f055f3b483c77b1c87f --explain
just ready d331ef4dbf830a1267859f055f3b483c77b1c87f
```
