# Validation and delivery

Qualified evidence observes clean exact source, declared inputs, tools, graph,
profiles and schema. Checks can write owned ignored output but cannot change
tracked source. Diagnostics can inspect dirty work and never issue readiness.

## Check execution

One dependency/verdict core serves diagnostics, member qualification and final.
Dependencies run in order, failed `requires` dependencies block descendants, independent
failures are collected, and a successful retry cannot clear a first failure.
A gate runs the shards it lists and the `requires` prerequisites whose output
they need. A shard's `after` prerequisites only order it among shards the gate
already runs and never add one; their failed verdict does not skip it, so one
round reports every failure. An infrastructure error in either kind still skips
dependents.
A shard command receives every engine value only through declared whole-argument
`{signetum.*}` placeholders; no engine value travels in the environment.
Configuration refuses unknown names, partial-argument use, placeholders in
findings commands, any but `{signetum.validation_workers}` in ratchet commands, and
`{signetum.schedule_file}` without `[validation] schedule_file`, a declared
validation input. `{signetum.recovery_report_file}` receives the runner's
retry-recovered nodes and `{signetum.validation_workers}` the allocated worker cap.
`{signetum.node_report_file}` receives first-attempt
`{"failed": [...], "passed": [...]}` with an optional `"unreached": [...]`; the
packaged pytest runner takes these as `--node-report`, `--recovery-report`,
`--workers` and `--schedule-file`. The engine reads it after the
shard ends, including after its time bound. Unreached entries fail the shard and
the result states their count. `{signetum.priority_nodes_file}` always exists and
holds the shard's owed entries as `{"schema_version": 1, "nodes": [...]}` for the
runner to schedule first; it never selects or satisfies an entry. A failed member, batch
or final gate writes a failure receipt for its workspace under the Git common
directory's `signetum/failures`, beside synchronization records. It names the
workspace, its changes, base, tip, first-attempt failed nodes, nodes that passed
only on retry and unreached nodes, all owed to the next gate. The next gate in that workspace releases a remembered node that an
observation in a change journal the workspace changed names as evidence with its
root cause, whether or not its shard is selected. Before checks start, it refuses
any other node whose shard is not selected again, and such a reselected node must
report passing in that run. A passing gate removes the receipt.
Same argv does not make distinct shards interchangeable. Only explicit successful
preparation can be reused within an operation.

Tree checks bind immutable source and tools. World checks observe mutable external
state, run fresh at final and never qualify reusable member evidence. A failing
finding-aware shard needs exact approved unexpired waivers for all findings;
empty/malformed reports, uncovered findings and expired waivers fail. Waived is
recorded separately from passed.

The repository owns uv preparation and build dependencies. Build clears stale
artifacts before installed tests. Static hooks do not duplicate the named Ruff,
format or ty owners. Member ratchets compare structured diagnostic multisets
against verified source, measured in a checkout of that source prepared by the
declared prepare gate and cached once measured. A baseline that cannot be measured
fails the shard with its cause and is never cached. Only a
`maintenance workspace-sync` merge with its trailer and local record moves that
baseline. A failed ratchet lists unrecorded merges and names `workspace-sync` and
`workspace-sync --batch`. Member and batch gate shards may declare
`{signetum.base}`, `{signetum.ratchet_baseline}` and
`{signetum.contribution_paths_file}`, a file holding
`{"schema_version": 1, "paths": [...]}` of repository-relative paths owned by the
member, excluding synchronized upstream changes; in a batch gate the base is the
increment start. The opening base remains immutable. Each member shard's receipt
details record these values, and admission and test inheritance require their
current values. In final and diagnostic runs a declared range value is an explicit
empty argument, meaning no range.

Resource allocation bounds nested workers. Settlement confirms an empty inventory
with a fresh snapshot inside its existing deadline. The supervisor settles positively
owned processes and scratch only; leaked or unobservable owned children refuse
success. Test measurements report actual phases/allocation without permanent
count/time gates. Mutable fixtures are independent; reuse only successful
immutable preparation. Required host suites remain complete. Repository pytest waits for cheap static
prerequisites; failed prerequisites block it. A collection error ends that run
without another full precollection pass or a passing qualification.

## Selection and efficient feedback

`ready` is the development loop; `ready --explain` shows its selection without
checks. `test run` delegates explicit targets or
a declared gate to the same supervisor and verdict core, without qualification.
Native arguments apply only to a shard; full exact-source gates reject them and
verify clean source plus input identities before and after execution.

No provider means the full declared member gate. An explicit provider binds
source, exact contribution, targets, tools and explanation; unexplained inputs
fall back, changed tests run whole and final never narrows. Member test
inheritance is per shard, with or without a provider: the paths changed since
the nearest verified ancestor member receipt are resolved by the impact rules and
any provider coverage, and each `inherit = true` member shard none of them affects
reuses that receipt's passing evidence for its exact command and matching input
identities. A rule or coverage affects the shards and gates it names and their
`requires` prerequisites; a modified test file is an ordinary path; an unexplained
path reruns every shard; a suffix of change journal events affects none. A shard
without such evidence, or one owing remembered nodes, reruns. Batch admission,
continuation and final never inherit.
Source admission still requires approved packages, intact journal ancestry and
resolved observations at ready, admission, continuation and final. Static checks still run.
Weighted scheduling and CI partitions are optional diagnostics; complete partition
aggregation checks exact membership/source and creates no lifecycle authority.

Admission and continuation select over the commits added since the batch's last
passing gate, starting at its recorded base, not the cumulative batch. They run
only the declared batch gate, resolved with any provider targets; it may run no
integration checks. Final stays complete, so cross-member failures surface there
rather than at admission. A remembered node whose shard the batch gate does not
run stays owed to final. Only a passing batch gate advances
that verified tip, so a refused or failed increment stays owed. One admission of
several members is one increment. A batch shard declaring
`{signetum.admission_base}` receives its start commit, so a project selector can
use the same range; elsewhere it is an explicit empty argument. A provider
selects a staged conflict resolution from a temporary detached checkout of its merge.

## Seven lifecycle operations

| Operation | Responsibility |
| --- | --- |
| `workspace-open branch base` | Record an immutable exact base and role before preparation; retries cannot change them. A base naming another open member's branch records that parent and its tip. |
| `ready [--explain]` | Qualify approved implemented changes by preparing and checking a temporary detached checkout of the clean exact member commit. Ignored files absent from that commit are absent from the check. The editing worktree stays. The result names each carried approval. This is the development loop; `--explain` only shows the selection. |
| `batch-open [--name slug] --member path ...` | Capture fresh delivery base and admit only named ready members. Only batch synchronization later advances that base. |
| `batch-admit --batch path --member path ...` | Merge captured qualified tips, prepare and run the batch gate covering the admitted selection. |
| `batch-continue --batch path` | Check resolved conflict state and its selection before completing its merge. |
| `final` | Reconcile and validate a frozen batch; emit source-bound receipt and review. |
| `batch-deliver source target expected-base expected-tip` | Publish only the reviewed exact candidate. `source` and `target` are existing worktree directories; the last two arguments are full commits. Confirm remote identity before moving target. |

Scope comes from actual committed paths and immutable registrations, never a
trailer inventing ownership. Qualification requires current approved contracts
and their implementation after exact approval: an own commit after the latest
approval commit binding the current contract. When none follows, ready refuses
naming that approval commit, and its expected action and the `status` next action
give the remedy: commit implementation after it, without counting the approval
commit's own changes or rewriting history. Competing retired formats supply
no fallback. Previously delivered intent remains protected; new intent needs its
own change. Ordinary execution refinements cannot reduce approved outcomes.

Named admission binds exact member receipt bytes, input identities and provenance.
The identity of the engine that ran `ready` is not a member input: an engine or
manifest-schema change admitted from a sibling does not strand a ready member,
whose tree, configuration, lockfiles and declared tools must still match exactly,
and the batch gate then checks the merged result with the admitting engine. Run
admission with the batch's engine, from the batch workspace when the repository
runs its own engine. An engine that cannot read a newer manifest names that path.
Real merge bodies carry member, original source and batch-base fields; titles
remain readable and ordinary merge hooks stay enabled. Batch names derive from
member tasks or an explicit `--name`; immutable registrations still own identity.
Publication uses `Merge <task> into <target>` with exact base/tip trailers.
Synthetic `commit-tree` publication does not invoke commit hooks; project-required
message checks belong in declared validation rather than an assumed hook. Opening an empty integration
workspace creates no provenance-only commit.
World evidence cannot replace tree evidence. Preparation or batch-gate failure retains
integration state for ordinary repair; merge conflict uses `batch-continue`.
Member synchronization records authorization before merging a verified source,
keeps the original base and distinguishes imported work from owned repairs.

A stacked member's workspace record names its parent member branch, and its base
is that parent's tip; the record is the only source of the chain. Its contribution,
selection and ratchet run from that base, excluding paths a verified parent sync
brought. Without `--batch`, `maintenance workspace-sync` in a stacked member takes
its parent while the parent branch exists and is not in the fetched delivery
branch, otherwise the delivery branch; a parent sync requires the new parent tip to
descend from the one held. Ready and admission refuse while the open parent branch
has moved past the held parent tip. Admission refuses a stacked member unless its
parent's latest admission in the batch, earlier in the same invocation or before,
is exactly that held tip or the tip is in the batch base. The final review's
`member_chain` names each member's own changes and, from its record, its parent.
The status next action names the needed sync or the admission order.

Batch synchronization is `maintenance workspace-sync` run in an open batch. It
merges the fresh delivery tip when that tip descends from the recorded batch base,
with `Signetum-Batch-Sync`, `Signetum-Batch-Base` and `Signetum-Previous-Batch-Base`
trailers, then advances the recorded base to that tip. This is the only change to
a recorded base. Admitted members stay admitted: provenance accepts each admission
bound to the base in effect when it merged and each synchronization that advances
it along delivered history, ending at the recorded base. The batch gate then runs
over the commits the merge added. A conflict stays open for `batch-continue`, which
advances the base after committing. `--batch` from a batch, rewritten delivery
history, an open merge or a dirty batch refuse without change.

Admission and batch synchronization compare the decision clause identities that
change records write in their contract decisions since the relevant base. Two
different changes writing one identity refuse before merging, naming the clause,
both changes and their owning workspaces; renumbering stays with those changes.
A member's claims come only from change records in its own contribution, not from
delivered records a verified synchronization brought into it.

## Final review and publication

Final rejects Proposed decisions added or modified within the declared decision
directory against its registered base; unchanged historical proposals remain
read-only context. Final reconciles selected source journals and affected standing answers. Pending
findings, inactive follow-ups, missing effective evidence or uncommitted source
suffixes refuse. Historical statements retain original proof without another
active workflow. Exact retirements preserve earlier answers. Final does not
append its own success to source.

A defect that appears only when members combine may be fixed by commits made
directly in the batch under the batch's own change record. Final attributes each
first-parent non-merge batch commit to the batch-owned changes approved before
it, unchanged at the tip; a commit touching only change records and decisions is
authority history. Any other direct commit refuses. Member-owned defects are fixed
in the member and admitted again; conflict resolution stays with `batch-continue`.
After a failed final on the current tip, status names both repairs.

Review binds approvals, source journals, admitted receipts, batch commit
attribution, recovered defects and remaining work. Recheck those inputs after validation and before publication;
changes require fresh final. The agent shows outcomes, scope, decision changes,
test modifications and evidence before explicitly authorized delivery. Existing
authorization remains valid within its agreed scope. Human
acceptance is a separate state. Final never allocates decision numbers or rewrites authority paths; stable
accepted filenames remain stable.

Publication recovery inspects exact local/remote holdings and resumes that same
operation. Never force-push, reset or substitute a direct merge. Structured result
statuses distinguish passed, invalid, failed, infrastructure error and conflict,
with retained diagnostics and the applicable recovery action.

## Workspaces and local maintenance

New linked trees live under the primary worktree's ignored `.worktrees`, with
explicit per-invocation paths independent of global defaults. Injective escaping
avoids percent signs that break ELF linkers. Refuse symlink escapes and occupied
paths before preparation; registrations identify branches, not machine paths.

Existing maintenance owns preparation, authorized synchronization, cleanup and
abandonment. Every workspace ends delivered, contained or abandoned. One removal
predicate serves cleanup, the sweep after every `batch-deliver` and the `status`
listing: a clean workspace that advanced from its base proves delivered when its
tip is an ancestor of the fetched delivery branch, and contained when every
non-merge commit outside that branch is patch-equivalent to one inside it and no
merge outside it has a dense combined diff, or when every path it changed since
the merge base has the same content there. Cleanup protects delivery,
user-selected and active-runtime checkouts, fresh bases, dirty or staged state,
open operations and uncontained or advanced tips. Explicit discard never removes
a changed index and needs an explicit selector. `workspace-abandon` removes only
uncontained work, with the owner's actor, confirmation source and reason bound
to the exact confirmed tip. Each removal retires the registration and writes a
retirement record with tip, outcome and proof under `signetum/retired`. An
`active_runtime` checkout can be removed from another checkout after the
invoking process finishes. There is no background deletion, readiness cleanup or
new public lifecycle operation. Status reads the last fetched delivery branch;
cleanup fetches again before it removes anything.

## Hosted checks and releases

CI and release share one reusable workflow and run the declared complete gate
against clean exact source without private workspace/approval/receipt setup.
Linux Python 3.12/3.13 and macOS Python 3.13 must all pass. Require every expected
coverage fragment from the current source/run before enforcing 90% project
coverage; a local or selected fragment is not that verdict.
Installed plugin and plain Skill source aliases resolve measured launcher and
installation paths to their maintained repository files before reporting; these
measurements remain in the coverage denominator. Retain failed output
for seven days with a bounded terminal preview.

Require passing hosted checks for the exact candidate before delivery. Tags,
package publication and external publishing settings require their own authority.
See [releasing](../maintainers/releasing.md) for that procedure.
