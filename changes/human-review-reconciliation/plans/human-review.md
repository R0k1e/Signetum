# Add human review and deviation reconciliation

Status: approved for implementation
Review: `changes/human-review-reconciliation/review.toml`
Specification: `changes/human-review-reconciliation/specs/human-review.toml`
Decision: `docs/decisions/ADP-human-review-brackets-reconciled-execution.md`
Base: `engine@29f1614cf57f7f3a61d10e5632bd9d552add156a`

## Evidence and authority

| Concern | Current authority | Planned outcome |
| --- | --- | --- |
| Approved behavior | Review and Specification traceability | Render an approval view; do not add an approval source file. |
| Execution state | No deterministic authority | Add a strict Git-common-dir deviation store. |
| Accepted rationale | `docs/decisions/` and batch numbering | Require explicit clarification or supersession for conflicts. |
| Validation | Existing exact-tree receipts and `final` | Add reconciliation preconditions while keeping final check-only. |
| Delivery | Existing explicit batch delivery | Generate a pre-delivery review without adding an operation. |
| Template | Deterministic `template/` render | Include minimal behavior and instructions, exclude engine history and local state. |

## Data flow

Human direction -> approved Review and Specification -> approval projection ->
member execution -> concurrency-safe common-dir ledger -> ready/member
provenance -> explicit batch -> pre-final authority reconciliation -> check-only
final -> structured review data -> delivery review -> explicit delivery.

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| APPROVAL | HRI-001 | Produce a concise approval projection from existing approved authorities. |
| LEDGER | HRI-002 | Store strict, member-provenanced deviations once per change under the Git common directory. |
| RECONCILE | HRI-003 | Validate terminal dispositions against Specification, Decision, architecture, test, and follow-up authorities. |
| REVIEW | HRI-004 | Produce a concise post-final comparison of commitment, result, evidence, deviations, authority changes, extras, and unfinished work. |
| LIFECYCLE | HRI-005 | Preserve the exact eight public operations, read-only final, explicit delivery, and engine/Template split. |

## Contracts and adversarial audit

- Product, member, and batch worktrees resolve the same logical ledger.
- Concurrent writers cannot create partial or interleaved records.
- Malformed, duplicate, or cross-change record identities are rejected.
- An empty ledger is valid and produces an explicit no-deviations projection.
- Pending or dangling records cannot produce a final receipt.
- A Decision conflict cannot be resolved by an uncited delivery explanation.
- A deferred approved commitment is disclosed as unfinished rather than
  summarized as complete.
- Re-running final neither mutates the frozen tree nor changes ledger state.
- Template rendering cannot copy engine change packages, Decision history, or
  local `.git/reposeal` state.

## File boundaries and dependency order

1. Approve this Specification and ADP.
2. Add engine behavior tests for strict records, storage, linked worktrees,
   concurrency, reconciliation refusals, and review projections.
3. Implement one engine deviation module and reuse existing Git/lifecycle
   adapters rather than adding a second command runner.
4. Extend lifecycle structured outputs and exact validation evidence only where
   required to bind the reconciliation digest.
5. Update the RepoSeal skill, agent contract, architecture, and focused workflow
   guide with the two-review interaction contract and recording threshold.
6. Render the minimal runtime and instructions into `template/`, then prove the
   clone-ready public artifact contains no engine-only state.

No public operation, watcher, direnv integration, compatibility parser,
downstream application policy, or external service is added.

## Acceptance commands

```text
uv run pytest tests/unit tests/integration/test_cli_manifest.py tests/integration/test_clone_ready_template.py
uv run pre-commit run --all-files
just changed engine --explain
just ready engine
```

The proposal-only worktree does not run `ready`; complete validation runs once
on the eventual frozen delivery batch.
