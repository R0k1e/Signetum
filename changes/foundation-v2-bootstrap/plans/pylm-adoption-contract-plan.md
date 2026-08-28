# PyLM Foundation v2 adoption contract plan

Status: future downstream plan; implementation blocked until Foundation v2 release
Specification: `changes/foundation-v2-bootstrap/specs/pylm-adoption-contract.yaml`

## Boundary

This Plan defines the required downstream work but does not authorize changes
in PyLM. PyLM must create and approve its own adoption ADP, Review, Spec, and
plan-owned worktree after an immutable Foundation v2 release exists.

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| ADOPT-01 | FIND-010, FIND-011 | Accept a PyLM-local adoption decision and create its first governed change package. |
| ADOPT-02 | FIND-010 | Declare active change paths and read-only legacy roots in PyLM repo.yaml and AGENTS. |
| ADOPT-03 | FIND-011 | Extend PyLM path consumers to new Spec and Plan paths without replacing repository authorities. |
| ADOPT-04 | FIND-011 | Bind Foundation version and digest into new validation evidence. |
| ADOPT-05 | FIND-011 | Install the exact repo-dev release and eliminate the drifting generic fork. |
| ADOPT-06 | FIND-010, FIND-011 | Validate, explicitly batch, final, deliver, and record acceptance in PyLM. |

## Expected PyLM paths

```text
changes/adopt-development-foundation-v2/**
docs/decisions/ADP-pylm-consumes-versioned-development-foundation.md
docs/architecture/change-lifecycle.md
docs/ARCHITECTURE.md
docs/architecture/validation-and-receipts.md
AGENTS.md
.agents/repo-dev/repo.yaml
.github/ci/checks/check_doc_links.py
.github/ci/checks/check_commit_message_format.py
tools/pylm_development/scripts/validation/validation_receipt.py
tools/pylm_development/scripts/merge_plan_delivery.py
tools/pylm_development/scripts/validation/quality_gate.sh
.pre-commit-config.yaml
associated tests
```

Existing `specs/` and `plans/` are neither edited nor moved.

## Required PyLM tests

- document and decision scanning accepts both legacy and active paths;
- commit `Delivers:` accepts active Plan paths and retains legacy support;
- receipts treat active change documents as development artifacts and bind the
  foundation identity;
- delivery discovers active Plan paths and cleanup preserves provenance;
- a new legacy-root document fails;
- all eight public operations retain their exact contracts;
- foundation mismatch invalidates new evidence;
- static validation composes foundation traceability without a second runner.

## PyLM execution sequence

1. Create the PyLM adoption decision proposal.
2. Receive human acceptance.
3. Create and confirm the PyLM behavior Spec.
4. Open the plan-owned PyLM worktree from the approved base.
5. Implement tests before changed production tooling.
6. Run targeted/changed evidence after coherent edits.
7. Commit coherent stages and run `ready <exact-base>` after each commit.
8. Stop clean and ready.
9. Wait for explicit batch authorization.
10. Run one final gate on the frozen batch.
11. Wait for explicit delivery authorization.
12. Deliver and record human acceptance or reopen.

## Acceptance

Foundation-side completion proves only that the adoption contract is available.
Program completion additionally requires a delivered and human-accepted PyLM
adoption change.
