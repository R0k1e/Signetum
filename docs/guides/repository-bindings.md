# Repository-owned customization

An adopted project owns its local authorities. Customize its actual product
bindings and use an explicit preview for later runtime updates.

## Replace product facts first

Current manifest schema 5 declares `repository.changes` for the change root,
`repository.decisions` for retained standalone decisions and `repository.architecture`
as optional responsibility context. Delivery is declared once in `[delivery]`. A change uses `change.toml` and its significant journal.
There is no separately versioned template or old Specification/Plan path alias.

Bind existing product commands and inputs. Do not create placeholder authorities,
copy a template, or add Signetum to the application's dependency groups. The Skill
owns execution tooling; the project owns its actual development environment.

## Preserve the lifecycle boundaries

If the repository keeps the Signetum lifecycle, keep its public operations
explicit and non-interactive. Repository commands may project existing
authorities but must not duplicate selector, receipt, merge, or delivery logic.
Technology profiles should be selected from repository evidence.

## Declaring a check which depends on the outside world

A shard whose verdict depends on state outside the observed tree declares
`evidence = "world"` and a `findings_command`. That command must emit the
Signetum findings document, so the translation from a tool's native output
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
follow_up = "changes/dependency-refresh/change.toml"
```

A waiver is ordinary reviewed repository content. It covers only the findings it
names, only for the shard it names, and only until it expires. Expiry is
mandatory: an expired waiver fails the gate rather than silently continuing. The
gate records `waived` in its evidence, so the delivery still states what it
carried and who approved it.

## Changing the process later

1. Record the consequential finding in the owning change journal.
2. Approve observable process behavior in that change.
3. Accept a standalone decision explaining the new authority and removed path.
4. Implement it in a change-owned worktree with behavior tests.
5. Deliver it through the repository's own batch lifecycle.

Another repository may manually implement the same idea as its own local
change. It does not pull an update from the upstream project.
