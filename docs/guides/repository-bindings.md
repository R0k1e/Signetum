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

A shard that needs the member's range declares `{signetum.base}`, the recorded
workspace base, and `{signetum.ratchet_baseline}`, the source of the latest
`maintenance workspace-sync`, otherwise that base. Use them for a project-owned
ratchet or diff instead of reading Signetum state files. The receipt records both,
and a receipt is not reused after either moves.

A shard's `ratchet_command` reports diagnostics for the member tree and for the
ratchet baseline. The baseline runs in a checkout of that commit prepared by the
`prepare` gate, so declare there whatever the command needs installed. A baseline
that cannot be measured fails the shard.

Admission and `batch-continue` run only the declared batch gate over the commits
added since its last pass. That gate may run no integration check: final stays
complete, so a failure that appears only when members combine surfaces at final.
A batch shard that declares `{signetum.admission_base}` receives the increment's
start commit.

A runner receives engine values only through placeholders declared as whole
arguments of its shard command; Signetum sets no environment variables for them:

```toml
[[validation.shards]]
name = "app:tests"
command = ["./scripts/test", "--priority-nodes", "{signetum.priority_nodes_file}",
           "--node-report", "{signetum.node_report_file}",
           "--workers", "{signetum.validation_workers}"]
```

| Placeholder | Value |
| --- | --- |
| `{signetum.priority_nodes_file}` | Path to the shard's owed entries, always created |
| `{signetum.node_report_file}` | Path the runner writes first-attempt node outcomes to |
| `{signetum.recovery_report_file}` | Path the runner writes retry-recovered nodes to |
| `{signetum.validation_workers}` | Decimal worker cap allocated to the shard |
| `{signetum.schedule_file}` | Absolute path of `[validation] schedule_file` |
| `{signetum.base}` | Recorded base in a member gate, increment start in a batch gate |
| `{signetum.ratchet_baseline}` | Latest workspace-sync source, otherwise that base |
| `{signetum.contribution_paths_file}` | Path to `{"schema_version": 1, "paths": [...]}`, the member's own repository-relative paths |
| `{signetum.admission_base}` | Batch increment start commit |

The last four values exist only in member and batch gates, and
`{signetum.admission_base}` only in a batch gate. Elsewhere, such as final,
`test run` or a member gate for the admission base, a declared one becomes an
explicit empty argument: there is no range, so validate everything. A
`{signetum.schedule_file}` without the `[validation] schedule_file` setting, any
other `{signetum.*}` argument, a placeholder inside a larger argument, or one in
`findings_command` is a configuration error. `ratchet_command` accepts only
`{signetum.validation_workers}`, since it measures two trees the same way. Entries are the runner's own stable ids: node ids,
or a file or directory path for a stage that never collected.

Write first-attempt outcomes to the node report as
`{"failed": [...], "passed": [...], "unreached": [...], "failed_checks": [...]}`;
`unreached`, `failed_checks`, `not_collected` and `non_failing` are optional.
`non_failing` maps exact node ids to runner-reported non-failing terminal outcomes,
for example `{"test.py::test_linux": "skipped"}`. Do not report collection or
deselection as a terminal outcome.
`not_collected` lists owed node ids absent from collection whose file was collected
in this run or no longer exists. Report collection before `-k`, marker or node
selection filters; never report a node from an existing file excluded from
collection. The engine releases these nodes only in a passing shard when a commit
since the remembered failure changed the file. Its `released_vanished_nodes`
receipt details name `node_id`, `retiring_commit` and `basis: "not_collected"`.
Omitting the field preserves the name-absence heuristic (`basis: "name_absent"`)
and journal-observation release. The packaged pytest runner accepts
`--priority-nodes {signetum.priority_nodes_file}` before `--` and computes this
report from the first collection, including xdist workers.
Write it before exiting, or progressively when the shard may reach its
`timeout_seconds`, since the engine reads it after a time-bound stop too. A failed
gate remembers failed and unreached entries for the workspace's next gate.
Unreached entries fail the shard and the result states their count.

A shard that runs several non-test checks, such as linters or document checks,
names the ones that failed in `failed_checks`, for example
`{"failed": [], "passed": [], "failed_checks": ["doc-links", "ruff-check"]}`.
They appear under that shard in the failure record's and the failed result's
`failed_shards`, beside its exit code; they are never owed or scheduled, and the
shard's exit status alone decides its verdict. Without a node report, or without
the field, the shard is listed with its exit code only. A ratchet shard lists the
rules of its new diagnostics.

The priority file always exists and holds `{"schema_version": 1, "nodes": [...]}`:
the entries this shard owes, unchanged, empty when none. Run them first, then the
rest of the same selection. It never narrows selection, and a failing owed entry
must not stop the others. An entry owed only because it was unreached is satisfied
when the node report lists that exact entry as passed or in `non_failing`, including
a declared skip. Receipt `discharged_by_reaching` entries retain its node id and
outcome. Failure or retry-recovered debt requires a reported pass; a later skip
does not erase it. A runner that reported a stage path must report that same path
with the applicable outcome. A remembered entry is also released
by a committed change record observation naming it as evidence with its root cause,
even inside a shard that is always selected.

A shard that should report its own failures even when a check before it fails
declares that check in `after` instead of `requires`:

```toml
[[validation.shards]]
name = "app:tests"
command = ["./scripts/test"]
requires = ["app:prepare"]
after = ["app:static"]
```

`after` orders like `requires` but does not skip the shard when the prerequisite
fails; the gate still fails and reports both. Keep prerequisites that produce
something the shard needs in `requires`. An infrastructure error in either kind
still skips the shard. A gate also runs the `requires` prerequisites of the
shards it lists, but `after` never adds a shard: an `after` prerequisite the gate
does not list is ignored.

Declare `inherit = true` on a tree test shard whose passing evidence may be reused
at ready, and name it in the impact rules for the paths that affect it:

```toml
[[impact.rules]]
name = "app.web"
paths = ["web/**", "tests/web/**"]
shards = ["app:web-tests"]
```

A fixup changing only `web/` then reruns `app:web-tests` and reuses the other
inheritable shards' evidence from the previous ready. A path no rule names reruns
them all, except a path inside a change directory, which affects no inheritable
shard. A commit changing only change records, with every contract unchanged, needs
no check at all: the previous ready evidence stands for it.

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
