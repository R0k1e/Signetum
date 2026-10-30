# Foundation v2 bootstrap and PyLM adoption plan

Status: approved for implementation
Plan owner: `plan/development-foundation-v2`
Approved base: `origin/main` at `7a789bfe21221ef2ff67f2ed0a4863933ab0b83f`
Specifications:

- `changes/foundation-v2-bootstrap/specs/foundation-product.yaml`
- `changes/foundation-v2-bootstrap/specs/change-traceability.yaml`
- `changes/foundation-v2-bootstrap/specs/repo-dev-agent-contract.yaml`
- `changes/foundation-v2-bootstrap/specs/immutable-release-and-ci.yaml`
- `changes/foundation-v2-bootstrap/specs/pylm-adoption-contract.yaml`

## Outcome

Turn the former Python CI/CD template into the single versioned authority for
generic development lifecycle mechanisms, implement requirement-to-acceptance
traceability there, and let PyLM explicitly adopt an immutable release while
retaining product-specific policy and leaving legacy `specs/` and `plans/`
untouched.

An active Plan never mutates `main`. It becomes durable provenance only when
the same validated, explicitly authorized delivery lands the implementation it
explains. Leaving a completed Plan forever on a disposable branch would break
the requirement-to-delivery chain after cleanup.

## Decision gates

Implementation cannot begin until these independent decisions exist and the
human changes each from `Proposed` to `Accepted`:

1. `docs/decisions/ADP-template-becomes-versioned-development-foundation.md`
2. `docs/decisions/ADP-change-packages-close-requirements.md`

The first decides product and release boundaries. The second decides the
durable Review/Specification/Plan/evidence/acceptance process.

## Current evidence

| Surface | Current authority | Finding |
| --- | --- | --- |
| Instructions | `CLAUDE.md` | Template and generic policy are mixed; ADP/ADR is incorrectly assigned to code comments. |
| Initialization | `scripts/init_repo.sh` | Placeholder rewriting, bare Python, hook installation, and local-state generation are template concerns. |
| CI | `.github/workflows/ci.yml` | Auto-fix mutates branches; tests and quality can observe different commits; auto-merge mutates main and deletes branches. |
| Release | `.github/workflows/cd.yml` | Publishes an example application and can skip publication when credentials are absent. |
| Package | `src/placeholder_name`, `main.py`, `config/` | Example application rather than reusable foundation mechanisms. |
| PyLM | PyLM repo-dev, checks, receipts, and delivery tools | Generic contracts may be extracted, but PyLM paths and product policy stay downstream. |

## Public contract

| Boundary | Before | Target |
| --- | --- | --- |
| Foundation selection | Clone and rewrite a template | Pin an immutable version and schema identities. |
| Specialization | Hard-coded Python stack | Repository manifest selects paths, profiles, validation, and delivery adapters. |
| Requirement closure | Conversation and prose bookkeeping | Review clauses, one Spec owner, exhaustive Plan obligations, evidence, and acceptance. |
| Agent guidance | Repository-local template instructions | Versioned repo-dev skill plus downstream safety contract and manifest. |
| Validation | CI tied to an example app | Check-only CLI and tests over manifests, changes, schemas, skills, and releases. |
| PyLM lifecycle | Eight repository-owned operations | The same eight operations; foundation supplies mechanisms, not a replacement runner. |

## End-to-end flow

```text
Human requirement
  -> downstream Review clause
  -> one approved Specification owner
  -> exhaustive Plan obligations
  -> implementation and behavior tests
  -> exact member receipt
  -> frozen-batch final receipt
  -> explicit delivery
  -> human acceptance or reopen

Foundation change
  -> foundation validation
  -> immutable release, schemas, repo-dev skill, and digests
  -> downstream adoption Review/Spec/Plan
  -> pinned-version update
  -> downstream validation and explicit delivery
```

## Single-authority table

| Knowledge | Sole authority |
| --- | --- |
| Generic lifecycle | One immutable Development Foundation package and repo-dev skill release. |
| Generic schemas | Foundation schema bundle. |
| Foundation compatibility | Foundation release metadata. |
| Repository paths and profiles | Downstream manifest. |
| User requirements and acceptance | Downstream `changes/<id>/review.yaml`. |
| Observable product behavior | Downstream approved Specifications. |
| Implementation sequence | Downstream Plans. |
| Current product architecture | Downstream architecture documents. |
| Validation and delivery evidence | Downstream receipt and delivery authorities. |
| Legacy PyLM contracts | Existing PyLM `specs/` and `plans/`, read-only. |

## Reuse and replacement

| Existing asset | Decision | Reason |
| --- | --- | --- |
| Git history and License | Retain | Preserve provenance and legal authority. |
| uv and Python quality tools | Extend as a profile | Useful but not universally mandatory. |
| Example application | Delete | Superseded by foundation mechanisms. |
| Placeholder initializer | Delete | Superseded by versioned adoption. |
| Auto-fix and auto-merge | Delete | Evidence and delivery must bind one immutable commit. |
| PyLM generic concepts | Extract by contract | Reuse semantics without moving PyLM facts upstream. |
| PyLM delivery implementation | Retain downstream initially | Avoid a high-risk big-bang extraction. |

## Document ownership

| Review clauses | Specification | Execution Plan |
| --- | --- | --- |
| FIND-001, FIND-002, FIND-009, FIND-012 | `foundation-product.yaml` | `foundation-product-plan.md` |
| FIND-003, FIND-005 | `change-traceability.yaml` | `change-traceability-plan.md` |
| FIND-004 | `repo-dev-agent-contract.yaml` | `repo-dev-agent-contract-plan.md` |
| FIND-006, FIND-007, FIND-008 | `immutable-release-and-ci.yaml` | `immutable-release-and-ci-plan.md` |
| FIND-010, FIND-011 | `pylm-adoption-contract.yaml` | `pylm-adoption-contract-plan.md` |

The umbrella Plan sequences the program. Each subordinate Plan owns its exact
files, tests, and acceptance commands; none may redefine another Spec.

## Work packages

### WP1 — Bootstrap foundation authorities

Clauses: FIND-001, FIND-002, FIND-012.

Create `AGENTS.md`, `docs/ARCHITECTURE.md`, the two ADPs, a specialization
manifest, and a minimal repository-owned validation and delivery protocol.
Replace `CLAUDE.md`; do not retain two instruction kernels.

Acceptance:

- routing begins at Architecture and the manifest;
- active Plans remain isolated until explicit delivery;
- delivered Plans remain as provenance;
- decisions are standalone files, never code comments.

### WP2 — Replace the template with a foundation package

Clauses: FIND-001, FIND-006, FIND-009.

Create the `development_foundation` distribution, manifest contracts, schemas,
profiles, and CLI. Delete the placeholder app, sample configuration, initializer,
and tests that only protect the retired template.

Acceptance:

- wheel and sdist contain schemas and CLI;
- package identity is queryable and immutable;
- Python, Node, Rust, Git, CI, and runner policy are selectable profiles.

### WP3 — Implement requirement closure

Clauses: FIND-003, FIND-004, FIND-005.

Implement strict Review, Spec, Plan, deferral, supersession, acceptance, and
reopen models plus a traceability checker. Derive implementation, integration,
and delivery states from typed evidence providers.

Acceptance:

- missing, duplicate, or superseded owners fail;
- every approved Spec clause maps to Plan obligations;
- unresolved deferral fails;
- ready, integrated, delivered, and accepted cannot substitute for one another;
- stdout is one versioned JSON value and diagnostics use stderr.

### WP4 — Publish and validate repo-dev

Clauses: FIND-003, FIND-004, FIND-005, FIND-006.

Move generic lifecycle guidance into the versioned `repo-dev` skill. Keep
repository paths and product facts downstream. Add focused references for
change closure, decisions, validation, delivery, and recovery.

Acceptance:

- skill validation passes;
- no PyLM path, branch, app, or selector is hard-coded;
- a forward test asking for half an approved Spec leaves the Plan open or
  requires an approved transfer;
- all four completion states remain distinct.

### WP5 — Make CI and release check-only

Clauses: FIND-006, FIND-008.

Every job checks out the same commit. CI never commits, merges, or deletes.
Release verifies exact final evidence and publishes immutable artifacts and
digests.

Acceptance:

- ordinary validation has no branch write permission;
- no auto-fix or auto-merge remains;
- package, schema, and skill identities are bound together;
- a requested publication cannot succeed when credentials are absent.

### WP6 — Release Foundation v2

Clauses: FIND-006, FIND-007.

After complete validation and explicit authorization, tag and publish the first
major foundation release. Remote rename, tag push, and publication remain
separate external mutations requiring authorization at execution time.

### WP7 — Adopt Foundation v2 in PyLM

Clauses: FIND-007, FIND-010, FIND-011.

Create a PyLM adoption ADP and change package. Pin the foundation identity,
declare active and legacy authorities, adapt hard-coded Plan/Spec consumers,
bind foundation identity into receipts, install the versioned skill, and retain
the exact eight public operations.

Acceptance:

- legacy PyLM `specs/` and `plans/` are unchanged;
- new additions under either legacy root fail;
- new change Plan paths work in commit, receipt, decision rewrite, batch,
  delivery, and cleanup logic;
- PyLM validation and delivery remain repository-owned;
- PyLM cannot silently consume another release.

## File boundaries

Foundation create or replace:

```text
AGENTS.md
docs/ARCHITECTURE.md
docs/architecture/**
docs/decisions/**
.agents/repo-dev/repo.yaml
changes/**
src/development_foundation/**
schemas/**
skills/repo-dev/**
profiles/**
tests/**
Justfile
mise.toml
pyproject.toml
.github/workflows/**
.pre-commit-config.yaml
```

Foundation delete after replacement tests exist:

```text
CLAUDE.md
main.py
config/**
src/placeholder_name/**
scripts/init_repo.sh
tests protecting only the placeholder application
```

PyLM changes only after Foundation v2 exists and its adoption ADP is accepted:

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
associated tooling and architecture tests
```

Do not modify or move existing PyLM `specs/` or `plans/`.

## Dependency order

```text
WP1 -> WP2 -> WP3 -> WP4 -> WP5 -> WP6 -> WP7
```

WP7 cannot implement against an unpublished or moving foundation branch.

## Through-case

1. A user requests a new PyLM behavior.
2. PyLM creates one Review clause.
3. One approved Spec owns it.
4. The Plan maps it to implementation and behavior-test obligations.
5. Dispatch briefs name obligations but cannot remove them.
6. Each member commit receives evidence for its exact SHA.
7. A frozen batch receives final evidence.
8. Explicit delivery lands code, Spec, Plan, and provenance together.
9. Review records acceptance or reopening against that delivery.
10. A status query answers what remains without an agent report.

## Adversarial audit

The implementation must reject:

- following `foundation/main` or `latest`;
- testing one commit while formatting or delivering another;
- a Plan omitting an approved clause;
- a dispatch brief redefining scope;
- deferral without an approved owner;
- two Specs owning one current clause;
- reporting ready as delivered or accepted;
- rewriting accepted history instead of reopening it;
- adding new PyLM files under legacy roots;
- embedding PyLM policy in the generic skill;
- a second selector, runner, watcher, alias, or public operation;
- remote publication or mutation without explicit authority.

## Validation strategy

After WP1 establishes the repository authority, bind these checks to exact
repository-owned commands:

```text
uv sync --locked
uv run pytest <targeted tooling tests>
uv run development-foundation check manifest
uv run development-foundation check traceability
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
<repo-owned repo-dev skill validation command>
```

Foundation final validation runs once on a frozen release candidate. PyLM uses
its repository selector, `ready <exact-base>` after each coherent commit, one
`final` on the frozen batch, and `batch-deliver` only after authorization.

## Approval checkpoints

1. Accept both foundation ADPs.
2. Confirm the exact foundation Specs.
3. Approve this Plan after decision and validation authorities exist.
4. Authorize Foundation v2 remote release.
5. Accept the PyLM adoption ADP and Spec.
6. Approve the PyLM adoption Plan.
7. Authorize PyLM batch creation.
8. Authorize PyLM delivery.
9. Record acceptance or reopening.

Approval at one checkpoint never implies a later external mutation.

## Completion criteria

- The former template has one supported foundation product identity.
- Generic lifecycle mechanisms exist only in the versioned foundation.
- Foundation consumes its own change-package protocol.
- CI and release evidence bind one exact commit.
- Review clauses are traceable through acceptance or reopening.
- repo-dev prevents silent scope reduction and distinguishes completion states.
- PyLM pins a release and keeps project facts downstream.
- PyLM legacy Specs and Plans remain unchanged.
- PyLM's eight operations, selector, receipts, and explicit delivery remain authoritative.
- No Plan reaches main before explicit delivery; every delivered Plan remains as durable provenance.
