# Quickstart

This guide starts with a repository created from the Signetum
GitHub Template and ends with one explicitly delivered, human-reviewable change.

## 1. Own the copied repository

Use GitHub's **Use this template** action, clone the new repository, and replace
the example product facts with your own. The new repository does not retain a
dependency or synchronization relationship with Signetum.

Inspect `mise.toml`, then prepare the declared toolchain:

```bash
mise trust mise.toml
mise install
uv sync --locked
```

Read `AGENTS.md`, `docs/ARCHITECTURE.md`, and `.agents/repo-dev/repo.yaml` before
changing files. The manifest must name the repository's actual architecture,
environment, policy, change, validation and delivery authorities.

## 2. Open isolated member work

Resolve the exact base and create the member workspace before authoring:

```bash
BASE=$(git rev-parse origin/main)
just workspace-open impl/health-endpoint "$BASE"
```

Continue inside the worktree returned by that operation. Trust its reviewed
`mise.toml` at that new path before using `just`. Follow architecture
and selected policies, report routing, and read `just protocol current`. While
coverage is `journal_only`, also inspect relevant declared historical decisions.
Original rationale is available through `just protocol history` on demand.

## 3. Confirm one change and implement it

```bash
just change-open add-health-endpoint
just protocol view changes/add-health-endpoint/change.toml
```

Fill that single draft with intent, stable requirements, observable acceptance,
exclusions, transfers, autonomy and execution steps before showing the view.
The view never grants approval. Record the owner's actual confirmation and exact
contract digest, then commit approval before implementation. Architecture,
process and security choices require an accepted identified decision proposal;
apply its exact clause edits through `just protocol reconcile`.

Use existing implementation and test owners. Capture significant findings and
standing answers through the journal tools, with a structured request and its
expected history digest. Do not add handwritten reports or duplicate current
decision summaries. Commit significant events before validating the source.
Run the repository's targeted commands, then:

```bash
just changed --explain
just ready
```

Both commands read the workspace's recorded base; neither takes a base argument.
Changed checks do not run the complete final gate or grant readiness. A first
failure remains failed after a diagnostic retry; fix it and run ordinary
validation again. Ready evidence binds the exact member tip. A later fix needs
a new commit and fresh readiness.

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
Explicit human acceptance remains separate evidence against that delivery; a
record marked complete does not imply it.

## What success means

- `ready`: one member commit passed its required member validation.
- `integrated`: that member is present in a named batch.
- `final passed`: the complete graph passed on the exact frozen batch tip.
- `delivered`: that validated tip reached the declared target and remote.
- `accepted`: a human explicitly accepted the named outcomes for that delivery.

No earlier state implies a later state.
