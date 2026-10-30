# Align development tooling with Perdura

Status: approved
Specification: `changes/align-perdura-development-tooling/specs/tooling.toml`
Base: `engine@b48d89059a4d31ce7eae42145e0cfc5be77666a2`
Source baseline: `Perdura product@b8b12a1379163f8380065d5f35c220eeee037e02` (verify before reuse).

The owner approved the preceding executable plan and authorized implementation on 2026-10-28. Work remains in this package's workspace and stops at clean ready. Delivery and publication are excluded.

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| IMPLEMENT-001 | ALIGN-001 | Extend lifecycle delivery; exercise a real bare remote with rejected push and interruption/retry. |
| IMPLEMENT-002 | ALIGN-002 | One result model consumed by CLI operations; verify all result/exit categories at command boundaries. |
| IMPLEMENT-003 | ALIGN-003 | Central evidence verdict; reject absent/stale/mismatched identity and preserve valid ready admission. |
| IMPLEMENT-004 | ALIGN-004 | Change ownership in workspaces, ledger, traceability and review projection; reject missing packages and plan-only readiness. |
| IMPLEMENT-005 | ALIGN-005 | Public sync/prepare/cleanup/discard with exact identity and retained-work diagnostics; real Git recovery scenarios. |
| IMPLEMENT-006 | ALIGN-006 | Number once before final under lock; verify repeated final and first-delivery scope. |
| IMPLEMENT-007 | ALIGN-007 | One selection consumed by diagnostic execution and member gate; prove final is never implicit. |
| IMPLEMENT-008 | ALIGN-008 | Port reusable validation contracts through adapters; deterministic contention, timeout, inheritance and ratchet scenarios. |
| IMPLEMENT-009 | ALIGN-009 | Generate template from canonical authorities and run common lifecycle cases against installed artifacts. |
| IMPLEMENT-010 | ALIGN-010 | Keep repository facts out of core and retain findings/waiver regression coverage. |

## Execution

Implement A (delivery/results/admission), B (change/workspace/final), C (validation), then D (template). Extend existing behavior tests before implementation. Inspect source and tests at each boundary; file lists are estimates until traced. Do not reduce scope to match an existing test suite.

Use `uv sync --locked`, focused `uv run pytest --no-cov <affected tests>`, and the declared `uv run pytest tests/unit tests/integration/test_cli_manifest.py`. Build with `uv build` and inspect wheel contents. Member and complete gates follow the repository lifecycle; no batch is opened without explicit instruction. The named test shard owns gate test execution; static hooks do not run a second full test suite. Record discoveries through the deviation API and reconcile before final.
