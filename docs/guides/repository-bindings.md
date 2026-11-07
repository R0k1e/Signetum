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

A member gate shard receives two full commits in its environment:
`SIGNETUM_BASE`, the recorded workspace base, and `SIGNETUM_RATCHET_BASELINE`,
the source of the latest `maintenance workspace-sync`, otherwise that base. Use
them for a project-owned ratchet or diff instead of reading Signetum state files.
Both are absent outside a member gate, so a check without them stays strict. The
receipt records both, and a receipt is not reused after either moves.

Declare a batch gate that covers what an admission can select. Without a provider
that is the complete member gate. A static-only batch gate refuses any admission
whose commits select a test shard. Batch shards receive the increment's start
commit as `SIGNETUM_ADMISSION_BASE`.

A batch shard that runs the project's own member selection over that range
declares the member shards it stands for:

```toml
[[validation.shards]]
name = "app:batch"
command = ["./scripts/check", "batch"]
covers = ["app:member"]
```

Admission then accepts a selected `app:member` when `app:batch` is in the batch
gate and passes. `covers` names only declared tree shards, never the shard itself,
and cannot form a cycle; manifest load rejects anything else. Keep it reviewable:
the covering command must really execute the covered shards' selected checks. A test runner that writes first-attempt
`{"failed": [...], "passed": [...]}` node ids to `SIGNETUM_NODE_REPORT` lets a
failed gate remember those nodes for the workspace's next gate. A remembered node
is released by passing again or by a committed change record observation naming
it as evidence with its root cause, even inside a shard that is always selected.

A runner opts into owed-first scheduling and unreached reporting by declaring
engine placeholders as whole arguments of its shard command:

```toml
[[validation.shards]]
name = "app:tests"
command = ["./scripts/test", "--priority-nodes", "{signetum.priority_nodes_file}",
           "--unreached-report", "{signetum.unreached_nodes_file}"]
```

The engine replaces only declared placeholders with absolute paths; any other
`{signetum.*}` argument, or one in `findings_command` or `ratchet_command`, is a
configuration error. Both files use `{"schema_version": 1, "nodes": ["<node id>", ...]}`
with the runner's own stable node ids. The priority file always exists and lists
the remembered nodes this shard owes, empty when none; run them first, then the
rest of the same selection. It never narrows selection, a failing owed node must
not stop the others, and an owed node is satisfied only by a reported pass.
Before exiting, or progressively when the shard may reach its `timeout_seconds`,
write the selected nodes that did not run to the unreached path. An absent or
empty file means none. Reported nodes fail the shard, the result states their
count, and the next gate owes them first.

A shard that should report its own failures even when a check before it fails
declares that check in `after` instead of `requires`:

```toml
[[validation.shards]]
name = "app:tests"
command = ["./scripts/test"]
requires = ["app:prepare"]
after = ["app:static"]
```

`after` orders and selects like `requires` but does not skip the shard when the
prerequisite fails; the gate still fails and reports both. Keep prerequisites
that produce something the shard needs in `requires`. An infrastructure error
in either kind still skips the shard.

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
