# Quickstart

This guide starts with a repository created from the RepoSeal
GitHub Template and ends with one explicitly delivered, human-reviewable change.

## 1. Own the copied repository

Use GitHub's **Use this template** action, clone the new repository, and replace
the example product facts with your own. The new repository does not retain a
dependency or synchronization relationship with RepoSeal.

```bash
mise install
uv sync --locked
```

Read `AGENTS.md`, `docs/ARCHITECTURE.md`, and `.agents/repo-dev/repo.yaml` before
changing files. The manifest must name the repository's actual architecture,
environment, policy, specification, Plan, validation, and delivery authorities.

## 2. Record the requirement

Create one stable change package:

```text
changes/add-health-endpoint/
  review.yaml
  specs/health-endpoint.yaml
  plans/health-endpoint.md
```

The Review records the human request as atomic clauses. The approved
Specification owns observable behavior. The Plan maps every owned clause to an
implementation obligation and exact evidence. Copy the teaching structure from
[`examples/complete-change`](examples/complete-change/README.md), then replace
all example identities and behavior with the real change.

Behavior changes require human confirmation of the Specification. Architecture,
process, and security decisions also require an accepted standalone decision.

## 3. Open isolated member work

Resolve the exact approved base and create a Plan-owned worktree:

```bash
BASE=$(git rev-parse origin/main)
just workspace-open impl/health-endpoint "$BASE"
```

Perform discovery before implementation: follow the architecture map, search
production and test implementations, identify the current authority, and record
the selected policy groups and reasons. Write behavior tests through the real
public boundary before adding new behavior.

During development, use the repository's targeted commands. `changed` explains
the selected validation impact without starting the complete final gate:

```bash
just changed "$BASE" --explain
```

Commit one coherent member and close it against the same base:

```bash
just ready "$BASE"
```

The ready receipt belongs to that exact commit. A later fix requires a new
commit and a new `ready` result.

## 4. Assemble an explicit batch

From the clean delivery worktree, name only the ready members intended for this
delivery:

```bash
just batch-open --member /absolute/path/to/health-endpoint-worktree
```

Add another independently ready member when needed:

```bash
just batch-admit /absolute/path/to/batch-worktree \
  --member /absolute/path/to/another-member-worktree
```

If admission creates a merge conflict, repair and stage the affected files in
the batch worktree, then continue only through:

```bash
just batch-continue /absolute/path/to/batch-worktree
```

## 5. Validate once and explicitly deliver

In the frozen batch worktree, run the complete check-only graph once:

```bash
just final
```

The result identifies the exact base and batch tip. Delivery is a separate human
decision. From the delivery worktree, pass those exact identities:

```bash
just batch-deliver \
  /absolute/path/to/batch-worktree \
  /absolute/path/to/delivery-worktree \
  <expected-base> \
  <expected-batch-tip>
```

Successful delivery reports the member identities, Plans, validated batch tip,
delivery commit, remote identity, validation evidence, and controlled cleanup.
Only after inspecting that delivery can a human record acceptance or reopening
against its delivery commit in the Review.

## What success means

- `ready`: one member commit passed its required member validation.
- `integrated`: that member is present in a named batch.
- `final passed`: the complete graph passed on the exact frozen batch tip.
- `delivered`: that validated tip reached the declared target and remote.
- `accepted`: a human accepted named Review clauses for that delivery.

No earlier state implies a later state.
