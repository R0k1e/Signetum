# Python template foundation-readiness audit

Audit date: 2026-08-28
Observed commit: `7a789bfe21221ef2ff67f2ed0a4863933ab0b83f`

## Scope

This is a read-only measurement of the repository before foundation
implementation. It records current facts and does not authorize or describe
future behavior.

## Findings

| Area | Evidence | Result |
| --- | --- | --- |
| Safety entry | `CLAUDE.md` | Present, but no `AGENTS.md`, architecture entry, or specialization manifest exists. |
| Product | `main.py`, `src/placeholder_name/`, `config/` | The repository is an application scaffold. |
| Initialization | `scripts/init_repo.sh` | Performs placeholder replacement, local environment creation, hook installation, and bare-Python file rewriting. |
| CI identity | `.github/workflows/ci.yml` | Test checks out the event SHA while post-auto-fix quality jobs can check out the branch head. |
| CI mutation | `.github/workflows/ci.yml` | Auto-fix commits to branches; auto-merge writes `main` and deletes branches. |
| Release | `.github/workflows/cd.yml` | Builds an application wheel and may skip PyPI publication when a token is absent. |
| Decisions | `CLAUDE.md` | Requires decisions in source comments; no standalone decision authority exists. |
| Requirement closure | repository inventory | No Review, Specification, Plan, receipt, acceptance, or reopen authority exists. |
| Agent lifecycle | repository inventory | Worktrees are requested but no repository-owned public operations or evidence protocol exists. |
| Profiles | `pyproject.toml`, `CLAUDE.md` | Python application choices are unconditional rather than selectable. |

## Reuse classification

| Asset | Classification |
| --- | --- |
| Git history and License | retain |
| uv packaging skeleton | extend |
| Python lint, type, test, and security configuration | extend into a profile |
| GitHub release skeleton | replace |
| CI auto-fix and auto-merge | delete |
| Placeholder application and initializer | delete |
| Example application tests | delete after replacement contract tests |
| Current instruction file | replace after the new safety contract is active |

## Validation owners currently absent

The repository has no current authority for:

- exact-commit receipts;
- a frozen final gate;
- decision identity and links;
- change traceability;
- foundation release compatibility;
- explicit delivery and cleanup.

The bootstrap Plan must establish these before implementation claims a
foundation release.
