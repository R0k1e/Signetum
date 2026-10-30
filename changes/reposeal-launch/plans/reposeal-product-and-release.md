# RepoSeal product and release plan

Status: approved
Specification: `changes/reposeal-launch/specs/reposeal-product-and-release.yaml`
Base: `main@0af4fe064f15e26c34df375daee8e7dd5f1b78ed`

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| SEAL-01 | REPOSEAL-001, REPOSEAL-005 | Replace current public product surfaces with RepoSeal and make the repository page the homepage. |
| SEAL-02 | REPOSEAL-002 | Add the approved canonical mark and derivatives produced only by scaling it. |
| SEAL-03 | REPOSEAL-001, REPOSEAL-002 | Extend product-surface validation for current identity and required assets. |
| SEAL-04 | REPOSEAL-003 | Rename the GitHub repository and update description, topics, badges, and social metadata where supported. |
| SEAL-05 | REPOSEAL-004 | Deliver, tag, and publish version 2.0.0 from one exact remotely confirmed source. |

## Authority and boundaries

- `README.md` remains the public homepage and product entry.
- `assets/brand/reposeal-mark.png` is the one canonical raster mark; all smaller
  files are deterministic scaling derivatives.
- The existing product-surface validator owns required asset and identity checks.
- GitHub repository settings own the remote name, description, topics, Template
  flag, social preview, and Release.
- Package and CLI identifiers remain internal machine contracts.

## Validation and delivery

```text
uv sync --locked
uv build
uv run pre-commit run --all-files
just changed 0af4fe064f15e26c34df375daee8e7dd5f1b78ed --explain
just ready 0af4fe064f15e26c34df375daee8e7dd5f1b78ed
just batch-open --member <member-worktree>
just final
just batch-deliver <batch> <target> <expected-base> <expected-batch-tip>
```

After remote `main` confirmation, rename the GitHub repository, update metadata,
create annotated tag `v2.0.0` at that exact source, and verify the release run.
