# Customizing the Template

A repository created from RepoSeal is an independent repository. Customize
its copied authorities directly; do not add an upstream Template dependency.

## Replace product facts first

Update the root README, architecture map, repository manifest, focused policy,
fixtures, examples, package metadata, and release targets with product facts.
Delete teaching artifacts that are not true for the new product; do not leave
placeholder aliases or fallback identities.

## Preserve the lifecycle boundaries

If the repository keeps the RepoSeal lifecycle, keep its public operations
explicit and non-interactive. Repository commands may project existing
authorities but must not duplicate selector, receipt, merge, or delivery logic.
Technology profiles should be selected from repository evidence.

## Declaring a check which depends on the outside world

A shard whose verdict depends on state outside the observed tree declares
`evidence = "world"` and a `findings_command`. That command must emit the
RepoSeal findings document, so the translation from a tool's native output
belongs to a profile or adapter, never to the lifecycle:

```json
{"schema_version": 1, "findings": [
  {"id": "GHSA-aaaa-bbbb-cccc", "locator": "pip:demo@1.0", "summary": "Leaks headers"}
]}
```

A world shard cannot appear in the member gate or in `member_required`; the
manifest rejects it. Schedule these checks in continuous integration as well,
because mutable state changes without any repository change.

## Waiving a world finding

When a world shard reports a finding the repository has decided to carry, add a
tracked waiver under `changes/<change-id>/waivers/`:

```toml
[waiver]
schema_version = 1
id = "audit-ghsa-aaaa-bbbb-cccc"
shard = "python:audit"
findings = ["GHSA-aaaa-bbbb-cccc"]
reason = "No fixed release exists and the affected path is unreachable."
approved_by = "maintainer"
expires = 2026-12-31
follow_up = "changes/dependency-refresh/plans/upgrade.md"
```

A waiver is ordinary reviewed repository content. It covers only the findings it
names, only for the shard it names, and only until it expires. Expiry is
mandatory: an expired waiver fails the gate rather than silently continuing. The
gate records `waived` in its evidence, so the delivery still states what it
carried and who approved it.

## Changing the process later

1. Record the need as Review clauses.
2. Approve observable process behavior in a Specification.
3. Accept a standalone decision explaining the new authority and removed path.
4. Implement it in a Plan-owned worktree with behavior tests.
5. Deliver it through the repository's own batch lifecycle.

Another repository may manually implement the same idea as its own local
change. It does not pull an update from this Template.
