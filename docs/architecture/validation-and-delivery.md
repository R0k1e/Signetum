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
`{"failed": [...], "passed": [...]}` with optional `"unreached": [...]` and
`"failed_checks": [...]`, the non-test checks that failed, reported only; the
packaged pytest runner takes these as `--node-report`, `--recovery-report`,
`--workers` and `--schedule-file`. The engine reads it after the
shard ends, including after its time bound. Unreached entries fail the shard and
the result states their count. `{signetum.priority_nodes_file}` remains an empty compatibility input. Failure
receipts retain only the current run's failed shards, checks, first-attempt
failures, retry-recovered nodes and unreached nodes. They never create debt for
a later gate; old ledgers are ignored. Unreached nodes and first failures fail
the current run. Final executes every repository-selected shard to completion
without failure or unreached nodes.
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

Resource allocation bounds nested workers. A shard receives
`min(workers, observed CPUs, affordable by worker_memory_mb)` workers through
`{signetum.validation_workers}`; the host operator's
`SIGNETUM_VALIDATION_WORKER_LIMIT` caps every shard on a shared machine. Each
shard's `resource_allocation` records the limit and the one-minute load average,
which never change the verdict: a first failure under load stays failed. A runner
that picks its own parallelism should take the declared cap instead. Settlement confirms an empty inventory
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
path reruns every shard; a path inside a change directory affects none. A shard
without such evidence reruns. Batch admission,
continuation and final never inherit.
Source admission still requires approved packages, intact journal ancestry and
committed journals at ready, admission, continuation and final. Observations never
block. Static checks still run.

A records-only range changes only paths inside change directories and keeps the
contract digest of every change record it changes: journal events, or approval
text that leaves the contract alone. Member evidence of a commit stands for each
descendant reached by a records-only first-parent range. `ready` there runs source
admission and no check and names the earlier receipt; admission, `status` and the
final review accept that receipt for the later tip. A contract change is not
records-only and needs a fresh ready, where inheritance still reuses every shard
the rest of the change leaves unaffected.
Weighted scheduling and CI partitions are optional diagnostics; complete partition
aggregation checks exact membership/source and creates no lifecycle authority.

Admission and continuation select over the commits added since the batch's last
passing gate, starting at its recorded base, not the cumulative batch. A
records-only increment runs source admission and no batch gate check. Otherwise they run
only the declared batch gate, resolved with any provider targets; it may run no
integration checks. Final stays complete, so cross-member failures surface there
rather than at admission. Only a passing batch gate advances that verified tip;
a refused or failed increment remains unverified. One admission of
several members is one increment. A batch shard declaring
`{signetum.admission_base}` receives its start commit, so a project selector can
use the same range; elsewhere it is an explicit empty argument. A provider
selects a staged conflict resolution from a temporary detached checkout of its merge.

## Seven lifecycle operations

| Operation | Responsibility |
| --- | --- |
| `workspace-open branch base` | Record an immutable exact base and role before preparation; retries cannot change them. A base naming another open member's branch records that parent and its tip. On a base whose manifest this engine cannot load, it opens with preparation `unavailable` and the cause, for the member that migrates it. |
| `ready [--explain]` | Qualify approved implemented changes by preparing and checking a temporary detached checkout of the clean exact member commit. Ignored files absent from that commit are absent from the check. The editing worktree stays. The result names each carried approval. This is the development loop; `--explain` only shows the selection. |
| `batch-open --actor owner --source approval [--name slug] --member path ...` | Capture owner authorization and fresh delivery base, then admit only named ready members. Only batch synchronization later advances that base. |
| `batch-admit --batch path --member path ...` | Merge captured qualified tips, prepare and run the batch gate covering the admitted selection. |
| `batch-continue --batch path` | Check resolved conflict state and its selection before completing its merge, then admit the members a conflicted admission left pending. |
| `final [--deliver --target path --actor owner --source authorization]` | Reconcile and validate a frozen batch; emit source-bound receipt, review and versioned publication binding. Explicit delivery options publish through the same delivery owner only after success. |
| `batch-deliver source target expected-base expected-tip` | Verify the lightweight publication binding and publish the exact candidate. `source` and `target` are existing worktree directories; the last two arguments are full commits. Confirm remote identity before moving target; report cleanup pending. |

Scope comes from actual committed paths and immutable registrations, never a
trailer inventing ownership. A member also owns each change package whose
`change.toml` its own first-parent non-merge commits wrote and its base lacks, so
a `workspace-sync --batch` that brings back the same record keeps it the member's.
When an admission stops at a conflict, the members named after it are recorded
under `signetum/pending-admissions`; the conflict result and `status` list them
and `batch-continue` admits them in order after committing the resolution. Qualification requires current approved contracts
and implementation for each carried package. Every own implementation commit
must have matching approval in its parent. Each package approved at the tip must
have covered implementation, including an exact accepted decision application
for authority-only work. Contract revisions after authorization are recorded only; final lists their
commits and changed fields per change, without requiring re-approval. Approval bundled with code remains
invalid even if later code follows it; history is never rewritten. Competing retired formats supply
no fallback. Previously delivered intent remains protected; new intent needs its
own change. Ordinary execution refinements cannot reduce approved outcomes.

Named admission binds exact member receipt bytes, input identities and provenance.
The identity of the engine that ran `ready` is not a member input: an engine or
manifest-schema change admitted from a sibling does not strand a ready member,
whose tree, configuration, lockfiles and declared tools must still match exactly,
and the batch gate then checks the merged result with the admitting engine. Run
admission with the batch's engine, from the batch workspace when the repository
runs its own engine. An engine that cannot read a newer manifest names that path.
A delivered manifest older than the engine is migrated in a member: workspace-open
opens on it without preparing, and status, batch opening, admission and
synchronization read only its identity, repository and delivery tables, the batch gate loads the merged manifest, and a member that
keeps the old manifest is refused when its own manifest is loaded.
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
keeps the original base and distinguishes imported work from owned repairs. Its
merge subject names the source branch once. A conflicted member sync is committed
with `git commit --no-edit` to keep its `Signetum-Sync` trailer; if the trailer was
lost, rerunning the same `workspace-sync` finds the merge of that source whose sync
record it wrote, records a recognition of that exact merge and reports
`recognized`. A merge without a sync record stays unverified.

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
read-only context. Final reconciles selected source journals and affected standing answers. Uncommitted source journal suffixes refuse. Pending observations and optional
resolution evidence do not block qualification. A deferral carries its
reason and an optional follow-up change, judged only when written; the review lists
every pending observation and deferred item in its top-level `unfinished_work`. Historical statements retain original proof without another
active workflow. Exact retirements preserve earlier answers. Final does not
append its own success to source.

A defect that appears only when members combine may be fixed directly in the
batch under its immutable authorization. `batch-open` requires `--actor` and
`--source` citing the owner's authorization and records them with a timestamp
and the initial members in its schema-2 workspace record. It creates no draft.
Final lists each implementation commit under `combination_repairs`, with its
subject, diffstat and authorization. No separate change or journal entry is
required; the batch may still record findings in integrated member journals.
Member-owned defects are fixed in the member and admitted again; conflict
resolution stays with `batch-continue`. Status names both repair paths.

Schema-1 batches retain batch-owned change authority. Each implementation commit
is attributed using the approved contract in its parent, without requiring the contract to match the later scope. Authorization is recorded
once; final review derives contract revisions since approval from source history.
That history starts at the first `change.toml` that parses as an approved record.
An earlier `change.toml` that does not parse is not authority and does not qualify
implementation. Final keeps each such draft on that change as `invalid_drafts`,
with its commit and the source parse cause. `approval_commit` is that first parsed
approval, and `contract_revisions` still lists every later parsed contract change.
A `change.toml` that does not parse after authorization fails review, including
when a later commit parses. Current parsing does not alias `approval.date` to
`recorded_at` or drop the extra field. The review
includes the authority and contract digests at the parent, including superseded
contracts. Old excluded drafts remain unused unless approved and committed as
legacy authority. Records-only commits are attributed to the records they touch.

`workspace-open`, `batch-open` and every successful preparation install or
verify the commit check. The machine-local shim at
`$(git rev-parse --git-common-dir)/signetum/hooks/reference-transaction` calls the
installed Skill launcher for Skill engines, so cache replacement during update
does not strand a hook on a removed interpreter. Repository engines use their
interpreter. `maintenance commit-check` reads the reference transaction on stdin.
The effective hooks directory honours `core.hooksPath`; Signetum preserves a
foreign hook and never writes into tracked source. A project-owned
`reference-transaction` chains the shim with this committable contract:

```sh
input=$(cat)
shim="$(git rev-parse --git-common-dir)/signetum/hooks/reference-transaction"
if [ -x "$shim" ]; then printf '%s\n' "$input" | "$shim" "$@" || exit $?; fi
```

Installation probes a temporary `refs/signetum/probe/` ref through Git; the shim
touches the probe before filtering branch refs, and the ref is deleted.
Status reports `active` or `inactive`, its cause and the chaining snippet;
it re-probes when the effective hook path or hook file changes. An inactive
check warns and does not refuse workspace opening. Git older than 2.28 cannot
run this hook. The same immutable attribution predicate remains the ready/final
backstop. Branch creation/deletion and other refs retain their existing rules; an
implementation commit still requires its parent approval. Before member sync,
batch sync or admission starts Git's merge, Signetum records the exact first
parent, source and prepared Signetum trailer lines in worktree-local Git state.
During the reference transaction, a candidate merge whose parents and pending
MERGE_HEAD match that operation must carry exactly those lines, including their
multiplicity. Subjects remain editable. Missing, changed, duplicate or extra
Signetum lines refuse before the branch moves, naming `git commit --no-edit`
and, for a batch, `batch-continue`. Ordinary commits and unrelated merges retain
their existing rules. The prepared message is independent of editable MERGE_MSG.
After a manual `--no-edit` commit, `batch-continue` accepts only the exact recorded
merge at HEAD, validates it and completes base advancement and pending admissions;
it also retains the staged-resolution path that commits with `--no-edit`.

Batch-open captures `engine = {version, implementation, source}` in its schema-2
workspace record. An installed Skill engine pins version and implementation;
a self-hosted repository engine pins its location inside the batch worktree,
because admission legitimately changes its source. Initial self-hosted admission
enters that batch's engine. A foreign checkout engine cannot open a batch: invoke
the installed Skill launcher instead. Admission, continuation, batch sync, final
and delivery refuse mismatches before work, naming the pin and the remedy:
finish with that engine or open a new batch for the same ready members.
There is no repinning operation. Legacy records without an engine remain
unpinned and status says so; members remain unpinned. A void validation names
each changed input and its before/after identities.

The commit check also refuses added or modified Proposed decisions using final's
predicate on the commit and its parent, and rewritten delivered commitments
using `changed_commitments`. The registered workspace base identifies delivered
packages; records first introduced in this workspace remain editable under their
existing rules. These record predicates also apply to records-only commits.


Final's review binds approvals, source journals, admitted receipts, batch commit
attribution, recovered defects and remaining work. Immutable object and ancestor
queries are reused only within that qualification's review lifetime. Final checks
the committed source and local evidence and authority fingerprints before and
after validation, then emits publication binding version 1. A receipt without
that versioned binding requires a new final. Delivery checks its exact commit,
base, target policy, review and evidence digests, and mutable local fingerprints;
it never reconstructs the semantic review or runs checks. Legacy discovery bytes
are fingerprinted without parsing their entries. Changes require fresh final.
The agent shows outcomes, scope, decision changes, test modifications and evidence
before requesting missing delivery authorization. Existing explicit authorization
remains valid within its agreed scope. `final --deliver` requires a target,
actor and authorization source and records that authority in the final binding.
Human
acceptance is a separate state. Final never allocates decision numbers or rewrites authority paths; stable
accepted filenames remain stable.

A historical records-only batch with no admitted members may still complete its
review, but has no publication provenance. Final reports publication unavailable
and emits no publication binding; admission is required before it can publish.

Publication recovery inspects exact local/remote holdings and resumes that same
operation. Never force-push, reset or substitute a direct merge. Structured result
statuses distinguish passed, invalid, failed, infrastructure error and conflict,
with retained diagnostics and the applicable recovery action.

Each push uses a temporary hook directory preserving all configured hooks. Its
pre-push guard requires the negotiated target old OID to equal the expected base
and the new OID to equal the delivery commit, then forwards the original hook's
arguments and input unchanged. Git receive-pack atomically compares that old OID.
No persistent hook or configuration is changed and no forced push is used.

## Workspaces and local maintenance

New linked trees live under the primary worktree's ignored `.worktrees`, with
explicit per-invocation paths independent of global defaults. Injective escaping
avoids percent signs that break ELF linkers. Refuse symlink escapes and occupied
paths before preparation; registrations identify branches, not machine paths.

Existing maintenance owns preparation, authorized synchronization, cleanup and
abandonment. An operation naming a workspace path, `workspace-abandon` and
`cleanup --worktree`, acts on that workspace's repository through its primary
checkout, whatever the caller's directory. A prepare shard may rebuild ignored or derived state; preparation
continues when it exits zero with the tracked source and index unchanged. A
failing prepare shard is refused with its name, full declared command and the
adapter's own `expected` when its last JSON output line carries one. Every workspace ends delivered, contained or abandoned. One removal
predicate serves maintenance cleanup and the `status`
listing: a clean workspace that advanced from its base proves delivered when its
tip is an ancestor of the fetched delivery branch, and contained when every
non-merge commit outside that branch is patch-equivalent to one inside it and no
merge outside it has a dense combined diff, or when every path it changed since
the merge base has the same content there. Cleanup protects delivery,
user-selected and active-runtime checkouts, fresh bases, dirty or staged state,
open operations and uncontained or advanced tips. Explicit discard never removes
a changed index and needs an explicit selector. `workspace-abandon` removes only
uncontained work, including a checkout created outside Signetum, and
`branch-abandon` a local branch without a checkout, each with the owner's actor,
confirmation source and reason bound to the exact confirmed tip; branch deletion
compares that tip atomically. An Agent may run either itself, citing in `--source`
where the owner confirmed that tip, such as the conversation; it never infers one. `leftovers` lists, read-only, unregistered checkouts
and uncontained branches without a checkout with their removal commands. Each removal retires the registration and writes a
retirement record with tip, outcome and proof under `signetum/retired`. An
`active_runtime` checkout can be removed from another checkout after the
invoking process finishes. There is no background deletion, readiness cleanup or
new public lifecycle operation. Status reads the last fetched delivery branch;
cleanup fetches again before it removes anything.

Publication leaves workspaces in place and returns `cleanup.status = pending`
with the existing maintenance command. Cleanup is a separate outcome; its
failure cannot change successful publication or its remote identity. No cleanup
queue or background deletion process is introduced.

Cleanup `--all-delivered` and cleanup `--branch` also select
local `change/*` and `batch/*` branches with no registered checkout, independently
of workspace-record existence. They require the same delivered/contained content
proof, then attempt non-forced `git branch -d`. Git refusal retains the branch and
reports its diagnostic; containment does not authorize forced deletion of a loose
branch. A successful branch-only removal retires its record, reports its tip and
proof in the existing removed list, and omits the worktree field. An empty
all-delivered sweep is a successful no-op. Other branch names and all branches
still registered to a checkout are excluded from the branch-only sweep.

## Hosted checks and releases

CI and release share one reusable workflow and run the declared complete gate
against clean exact source without private workspace/approval/receipt setup.
Linux Python 3.12/3.13 and macOS Python 3.13 must all pass. Require every expected
coverage fragment from the current source/run before enforcing 90% project
coverage; a local or selected fragment is not that verdict. Only the final gate's
`engine:coverage` shard measures coverage; member and batch gates run the same
tests in `engine:pytest` without it.
Installed Skill source aliases resolve measured launcher and
installation paths to their maintained repository files before reporting; these
measurements remain in the coverage denominator. Retain failed output
for seven days with a bounded terminal preview.

Require passing hosted checks for the exact candidate before delivery. Tags,
package publication and external publishing settings require their own authority.
See [releasing](../maintainers/releasing.md) for that procedure.
