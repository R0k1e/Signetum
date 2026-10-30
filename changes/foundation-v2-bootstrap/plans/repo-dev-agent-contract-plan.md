# repo-dev agent contract plan

Status: approved
Specification: `changes/foundation-v2-bootstrap/specs/repo-dev-agent-contract.yaml`
Base: exact approved Foundation bootstrap base after change-closure contracts are stable

## Preconditions

- The change closure models and manifest contract are stable.
- The generic skill location and release packaging contract are approved.
- Use the skill-creator workflow and validate the result before delivery.

## Obligations

| ID | Clause | Outcome |
| --- | --- | --- |
| SKILL-01 | FIND-004 | Rewrite the generic entrypoint around manifest-driven requirement closure. |
| SKILL-02 | FIND-004 | Add focused references for change closure, decision/spec/plan gates, validation, delivery, and recovery. |
| SKILL-03 | FIND-004 | Package skill version and digest with the foundation release. |
| SKILL-04 | FIND-004 | Forward-test scope narrowing, path discovery, completion reporting, and reopen behavior. |

## Target structure

```text
skills/repo-dev/
  SKILL.md
  references/
    change-closure.md
    spec-plan-decisions.md
    worktree-validation.md
    delivery-recovery.md
```

The entrypoint contains routing, stopping conditions, and high-frequency
invariants. Detailed schemas and conditional procedures belong in references
and are loaded only when their mode applies.

## Required instruction changes

- Add Requirement closure before Planning.
- Require one current Spec owner for every affected Review clause.
- Require exhaustive Plan obligations.
- State that dispatch selects obligations and cannot alter scope.
- Require an approved transfer before deferral.
- Distinguish ready, integrated, delivered, and accepted.
- Define new requirement, changed accepted behavior, implementation defect, and
  omitted-requirement reopen paths.
- Read concrete paths, profiles, commands, and branches from the downstream
  manifest.
- Preserve authorization boundaries for batch, delivery, publication, and
  other external mutation.

## Removed guidance

- Any PyLM-specific path or operation count in the generic skill.
- Repeated generic coding advice already supplied by the model or downstream
  policy.
- Missing or unreferenced supporting resources.
- Examples that accidentally turn one repository's policy into a universal
  constraint.

## Forward validation cases

1. The user approves four phases; a dispatch asks for phases one and two only.
   Expected: the skill keeps the Plan open or requires an approved transfer.
2. A repository manifest uses `work/` rather than `changes/`.
   Expected: the skill routes to `work/` and never invents `changes/`.
3. A member receipt passes but no delivery exists.
   Expected: the skill reports ready, not delivered or accepted.
4. Human rejection follows delivery.
   Expected: the skill records reopen/supersession and does not rewrite history.
5. Foundation vNext is installed but the downstream manifest pins vCurrent.
   Expected: mutation stops on version mismatch.

## Validation

```text
<skill-creator quick_validate> skills/repo-dev
uv run pytest tests/unit/skills
uv run pytest tests/integration/test_repo_dev_forward_cases.py
uv run development-foundation skill inspect repo-dev
just changed <exact-base> --explain
just ready <exact-base>
```

The final repository commands must resolve the environment-owned skill-creator
validator without committing a machine-specific absolute path.
