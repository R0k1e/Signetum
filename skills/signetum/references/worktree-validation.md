# Work and validation

Use the registered member workspace and its immutable base. Ready prepares and
checks a temporary detached checkout of that committed tip, so an ignored file
that is not in the commit cannot satisfy preparation. The editing worktree stays.
Use a short task branch such as `change/isolate-runtime`, never an opaque identifier.
Follow the project's commit convention. Subjects describe a durable outcome; keep
related changes together instead of committing each journal event separately.
Use concise specific change bullets when the project requires them, and explain
removed or replaced authorities. Keep decision rationale in its owning change,
not repeated in commit messages; omit transcripts and command logs. Commit human
approval before implementation and preserve commits already bound to evidence.
If ready refuses as plan stage, add an implementation commit after the named
approval commit, as its expected action and `status` say; changes inside that
commit do not count. Never amend, rebase or reorder history to fix it.
`workspace-open` and `batch-open` install a `reference-transaction` hook that
applies the same rule to each new commit. In a member, a commit changing anything
outside change records and decisions needs matching approval in its parent, so
commit the approval on its own first. In a new batch, combination fixes use the
authorization recorded at batch-open; legacy batches need parent-approved
batch-owned changes. Later re-approval does not invalidate earlier implementation. Records-only commits
and merges pass. It needs Git 2.28; final and ready still check.
When a declared tool such as `wt` is missing from the default Mise environment,
Signetum runs it under the one environment the project declares for it
(`mise.<env>.toml`); otherwise the refusal names the `MISE_ENV` to set.

Only `workspace-open` creates a registered worktree. Read history with read-only
commands (`git log/show/diff/blame`, `git show <commit>:<path>`). When a full older
tree is needed, extract it in a scratch directory with `git archive` or a throwaway
`git clone --shared`, never `git worktree add`. Inspect another worktree with
`git -C <path>` instead of `cd`. Never run the product or tests against the
owner's real instance, credentials, ports or personal browser.

Find and extend the existing implementation owner. Reproduce changed behavior
through its public boundary and validate the approved contract with the existing
runner. Without a selection provider, run the full declared member gate. An
explicit provider may select checks; this skill does not select an application
language or replace its test system.

Choose the cheapest layer that can expose each distinct risk. Pure rules and
input combinations belong in unit/property tests; integration traverses necessary
public boundaries. Use installed artifacts or a complete lifecycle only when that
boundary is at risk. Configuration/component matrices use supplied values and minimal materials;
repository acquisition and source binding have their own necessary real tests.
Do not create a Git repository, install an environment or copy the full product
for each pure rejection case. State the risk briefly in the existing execution plan, not
in another test inventory. A documentation rewrite alone needs link/static checks,
not a new behavior suite.

Before changing tests, classify existing affected evidence as retain, extend,
merge, replace, delete or new. Keep necessary real traversals for distinct public
contracts and put pure matrices in core tests. Generated/installed execution
checks their own boundaries; it does not mechanically repeat every shared case.
Tell the user the affected test files, reason and retained or replacement evidence
before modifying them. Explicitly disclose removed coverage, relaxed assertions,
new skips and threshold reductions; a green result does not justify weakening an
approved obligation. Summarize test changes and actual checks in the final user
review without creating a separate test report.

Add only functional tests that drive observable behavior through a real boundary.
Do not add implementation-shape, vocabulary-scan, key/catalog-presence or
mapping-table tests, and do not assert runtime-generated sentences verbatim.
Tests never read real credentials or the real home.

Do not pin teaching prose or private call order. Keep mutable test resources
independent and reuse only successful immutable preparation. Independent consumer
fixtures isolate caller-only test/interpreter configuration while retaining
enclosing allocation and process-ownership markers.

Use `status` for the current workspace, findings, recorded evidence and next step;
it lists unresolved findings with counts, and `status --verbose` adds resolved ones.
`ready --explain` displays the check plan without executing it. Status does not
requalify tools or grant readiness. `ready` is the feedback loop: commit, run it,
fix, commit and rerun until it passes on the current tip.

For explicit development feedback, use the repository's configured diagnostic
utility: `test run --shard <declared-shard> -- <native-test-arguments>`. It appends
arguments to the existing command, preserves its declared targets and uses the
normal allocator and supervisor without registration or readiness evidence.
Prepare its environment and required build inputs first. Native runner options
are repository-specific; the skill does not guess a framework or rewrite argv.
Do not independently multiply worker counts inside an enclosing parallel run.
A runner bounds its parallelism by the shard's declared `workers` and
`worker_memory_mb` through `{signetum.validation_workers}`; on a shared machine the
operator caps every shard with `SIGNETUM_VALIDATION_WORKER_LIMIT`. A first failure
under load still fails; the receipt records the allocation and load average.
Use observed setup/call/teardown and phase cost to decide whether a wider shard
or grouping helps. Do not introduce a permanent timing/count gate or handwritten
test inventory. Stop repeating verification once relevant checks pass unless a
new change or unresolved concern requires another run.

When `maintenance workspace-sync` stops on a conflict, resolve the paths and
commit with `git commit --no-edit`, which keeps the pre-filled `Signetum-Sync`
trailer. If the trailer was lost, rerun the same `workspace-sync`: it recognizes
the merge it recorded, so the source's paths stop counting as the member's own.

## Significant records

Read this section when a finding needs a durable answer.

Use `change record` for a finding that changes implementation, authority, scope or the
delivery explanation. Use `change resolve`, `change retract`, `change reconcile` or `change retire` for its
standing answer and accepted decision changes. Ordinary writes take semantic
arguments; the tool binds the current approved change and history identity:

```text
change record --id finding --requirement REQ-001 --summary "What was found" --reason "Why it matters"
change resolve --id fix --target <observation-id> --reason "What resolves it" --evidence <source-path>
change reconcile --id accepted-decisions --reason "Apply the approved proposals" --accept-decisions
```

Use the returned observation ID as the exact resolution target; the record's
`--id` also works. `change resolve --help` shows every form with examples. `--id` is a
stable retry identity: the same content is idempotent; changed content needs a
new identity. Add `--change` when more than one approved change matches the
workspace base. `--expected-history` can explicitly bind a previously reviewed
view; a stale write refuses. Evidence is a path in the current tree or the name of
a validation receipt; resolve writes a pytest node id `path::test` as its file.
Writes in other worktrees never wait for each other. `change why <clause-id>`
shows one decision clause's revisions, reasons, approval source and commits. A deferred resolution uses `--disposition deferred` with a
`--reason` that says who decided and what remains owed; an optional `--followup
change-id[#REQ-ID]` names an approved change on any local branch. The final
review lists every deferral under `unfinished_work`. A commit that changes only
change records keeps the member's ready evidence: `ready` starts no check, and
re-admission runs no batch gate. In a batch, the same commands record, resolve or
defer findings of the changes it integrates; commit them there, and final checks them.
`change retract` takes the target and exact prior `--resolution` ID.

### Conditional atomic edits

Read only for an atomic combination or exact evidence retirement.
The advanced structured `--request` plus `--expected-history` path remains for
atomic combinations and exact evidence retirement. Do not mix it with semantic
fields. Both paths use the same locked writer and committed approval. On refusal,
no write occurred: inspect the reason, commit changed authority bindings if
needed, and verify the returned applied transaction after retry. Never force a
replacement or edit JSONL. Ordinary command output stays in local logs.

Commit significant source events before validation freezes the source. Run the
repository's targeted checks during work and its member gate for ready. A first
failure remains failed even when a diagnostic retry passes; after fixing it,
run ordinary validation again. A failed gate remembers its failed and retry-only
nodes for the workspace. Its failure record, `signetum/failures/<workspace>.json`
under the Git common directory, and the failed result's `failed_shards` list every
shard that did not pass with its exit code and the failed checks its runner
reported. Read them, fix every listed failure in one round, then run ready again;
the `cause` alone may name only part of them. A committed `change record` observation that names a node
with `--evidence <node-id>` and states its root cause in `--reason` releases it,
even when its shard is still selected. Otherwise the next gate refuses before checks
unless the node is selected again, and then it must pass. Moving a failed test out
of scope never offsets that failure, and neither does a retry-only pass. A shard
command that declares `{signetum.priority_nodes_file}` receives those owed nodes
as `{"schema_version": 1, "nodes": [...]}` to run first. Node outcomes come only
through a declared `{signetum.node_report_file}`, whose optional `unreached` list
fails the gate and makes those entries owed; its optional `failed_checks` names
non-test checks for the record and is never owed. Every other engine value, such as
the base, ratchet baseline, contribution paths, admission base, worker cap,
recovery report and schedule file, is also a declared `{signetum.*}` argument;
Signetum sets no environment variable for a runner. See the
[repository binding guide](https://github.com/R0k1e/Signetum/blob/main/docs/guides/repository-bindings.md)
for the runner contract and order-only `after` prerequisites. Process settlement checks only positively owned
jobs and refuses successful commands that leave owned children behind.

Preserve unrelated files and processes. Stop at a clean ready unless integration
or delivery is authorized. Validation never appends its own success to source.

For explicitly requested project selection, weighted pytest scheduling or CI splitting,
read [optional validation optimization](validation-optimization.md). Keep these
opt-in; do not expand every repository adoption to include them.

## Coordinating parallel members

Read only for multiple members or integration coordination.

Before delegating, the coordinating Agent names each member's outcome, worktree,
owned scope, dependencies and shared interfaces in the existing execution plan.
Resolve shared contract choices before dependent implementation; synchronize through
the declared owner instead of changing another member's worktree. Independent
members can proceed while an affected choice is pending.

Keep mutable dependencies, reports and scratch local. Bound concurrent gate runs
at the caller; per-operation and nested limits are not a host-wide scheduler.
The named integration owner admits exact ready tips, handles conflicts and runs
complete final. A later member change needs fresh ready and admission. A clean
Git merge does not establish semantic compatibility; validate the integrated
behavior and reconcile conflicting decisions through the ordinary protocol.

### Stacked members

Split one large change into a chain of smaller changes, each with its own
approved change record. `workspace-open <branch> <parent-branch>`, naming another
open member's branch as base, records that parent and its exact tip as the
immutable base; approve the child against that base. The child's ready selects
only its own contribution and still checks its complete tree. When the parent
commits again, ready and admission in the child refuse until
`maintenance workspace-sync` in the child merges the parent's new tip; a stacked
member syncs from its parent until the parent is delivered. Paths it brings are not
the child's contribution. Never rebase a member onto its parent. The `status` next
action names the needed sync or the admission order.
