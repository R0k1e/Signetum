# Validation and delivery responsibilities

Ordinary validation is read-only and observes one exact commit. Evidence binds
Signetum, schema, profile, commit, and check identities. A successful member
check is not batch integration, delivery, or human acceptance.

The member and final gate build the source distribution and wheel before the
repository check graph. Integration tests therefore consume release inputs
created from the exact tree under validation, never a `dist/` directory left by
an earlier command in one worktree. The same gate also invokes the locked Ruff
check and format contracts, Bandit scan, and dependency audit used by CI; the
local pre-commit Ruff hooks use that same locked version. The complete gate
skips those two hooks because their named Ruff shards already own execution.

The named pytest shard owns gate test execution. Pre-commit composes static
hooks only, so inherited member tests are not secretly rerun by a static hook.
The declared complete operation is the configured final lifecycle gate.

Whole-corpus tree checks may declare a `ratchet_command` which emits one
version-one diagnostic document: `schema_version = 1` and a `diagnostics` array
of repository-relative `file`, `rule` and `message` records, with optional
positive `line` and `column`. Repeated equal records retain their counts;
positions do not identify a diagnostic. A member compares the current
multiset with the newest supported synchronized source, or its recorded base
before any synchronization, and refuses only additional occurrences. Final,
batch checks and conflict continuation always run the strict `command`.
World checks and inherited test shards cannot declare a ratchet.

A diagnostic command exits zero only after it measured the tree. An invalid
or unavailable current measurement is infrastructure failure, never an empty
finding set. An unavailable baseline is explicitly reported and compared as
empty; it is never cached. Successful baseline measurements are cached outside
the tree by source commit, command, observed tools and runner implementation.
The snapshot uses a temporary archive plus an isolated Git inventory, without
registering a worktree; a refresh verifies the extracted files against the
committed tree, including export attributes. Traceability and ty adapters
translate their structured reports into this protocol. The named ty shard,
rather than a duplicate static hook, owns type-check execution. Python check
identity includes installed package versions and actual implementation bytes,
so editable tool changes cannot reuse a stale baseline.

Every shard declares an evidence class. A `tree` shard is a pure function of
the observed tree and the bound tool identities, so a successful identity stays
successful. A `world` shard also reads mutable state outside the tree, such as
a vulnerability advisory database, so it can begin failing without any
repository change. The member gate accepts only `tree` shards, and member
narrowing defers a `world` shard reached through an impact rule to the final
gate rather than letting state the member does not own block its closure. A
`world` result records the instant it observed the world and is never a
reusable admission credential.

The engine pytest corpus partitions these classes with the `world` marker.
The member test command excludes that marker, while the final-only world test
shard runs native external-state scenarios without inheritance. The independent
rendered-template member case still runs in the tree shard; its final case
creates a real batch, consumes the member's ready receipt, and performs the
native dependency audit. Collection checks prove that the two declared commands
are disjoint and together cover the full test corpus.

A failing `world` shard runs its declared findings command and reports through
the tool-neutral Signetum findings document; Signetum never parses a tool's
native output. Each reported finding is matched against the waivers tracked
under `changes/<change-id>/waivers/`. The shard is `waived` only when every
reported finding is covered by a waiver that has not expired. An uncovered
finding, an expired waiver, a missing findings command, an unparsable document,
and a failure that reports nothing all fail the gate. Evidence records `waived`
separately from `passed` together with the covering waiver and finding
identities, so a delivery states which known unrepaired findings it carries and
under whose authority.

A change package owns one isolated implementation branch from proposal through
approval and implementation. The shared Git state binds its owner at the first
discovery or readiness check and refuses a second implementation branch. A
member is ready only with approved behavior and required decisions plus its own
implementation commit after approval. A consolidated authority-only change can
qualify through its own commit introducing an exact approved decision application
in the source journal. The existing source reviewer verifies the committed
history, approval proof and current contract; qualification checks that the event
was newly introduced by a non-merge commit on this member's first-parent history.
Approval-only edits, ordinary observations and decisions merely borrowed through
a merge do not constitute implementation. A package-only member remains plan
stage. A member without a carried approved change package is refused before
checks and admission, even when it has an otherwise matching test receipt.
Readiness and final validation require member and batch workspace roles respectively.

Actual committed paths identify each batch's first-delivered changes and their
Plans; a trailer cannot omit or invent delivery scope. Final reviews first-delivered
packages and lists historical Plan edits separately. Its reconciliation also
covers discoveries associated with every exact admitted member, including
packages whose approval was delivered earlier. It does not reopen their approval
or include unrelated active members. New discoveries bind the observed source
commit; later unadmitted commits do not enter an earlier batch. Legacy discoveries
without a commit remain conservatively visible. Once the later tip is admitted,
its retained discoveries must also reconcile. Delivered Review and
Specification edits are refused except for exact decision-numbering substitutions.
A later intent requires its own change rather than rewriting accepted history.

A workspace owns its base. `workspace-open` records the resolved base under the
machine-local state root at `signetum/workspaces/<branch>.json`, and it is
written once. `changed` and `ready` take no base argument; they read that
record, and a workspace without one fails as a precondition rather than having
a base derived for it. A batch is a workspace which declares its members, so it
carries the same record and its base is read the same way. The
`Signetum-Batch-Base` trailer stays in the provenance commit as durable
attestation, and delivery refuses a batch whose record and trailer disagree; no
operation recovers a base by searching commit prose.

A member's recorded base never changes. `maintenance workspace-sync` optionally merges an
exact delivery or verified batch snapshot without preparing dependencies.
Member path selection excludes unchanged inputs imported by supported sync
merges, so siblings' packages do not become the caller's ownership. Changed
lockfiles or generated inputs are followed by explicit worktree preparation.
Readiness remains a judgement of the member's own implementation.

Supported synchronization records source authorization under shared Git state
before merging. It binds the recorded base, previous tip and exact verified
delivery or batch source. Conflict resolution may complete that same merge;
a commit trailer alone cannot authorize a source. Member path selection tracks
own first-parent edits, adopted source content and hand repairs. Restoring
original-base content after a sync remains an owned repair when it differs
from the synchronized source; reverting an own edit to inherited content does
not claim a sibling's package. The recorded base itself never changes.

Admission requires successful member-safe evidence bound to the exact member
commit, tree, recorded base, configuration, graph, profiles, lockfiles and tools.
A completed final gate can supply those checks when its complete input identity
matches. World outcomes never substitute for tree evidence. A new tip requires
fresh readiness even when its tree is unchanged. Selection's requires_final
flag declares additional batch responsibility and never waives member checks.

Admission requires the member graph's dependency closure, not just its named
root checks. Ratchet results must still qualify against the currently verified
source; losing or changing that qualification requires fresh readiness.
Strict final evidence remains a stronger alternative for the same exact tip.

With an explicit selection provider, only tree test shards declaring
`inherit = true` may reuse the
nearest receipted first-parent ancestor in the member's `base..HEAD` range.
The ancestor's committed tree and file inputs must verify, and base,
configuration, profiles, graph, schema, lockfiles and current tool identities
must still match. Every intervening path must be explained and select no
inheritable test, including through gate/dependency expansion; changed tests
always prevent inheritance. An incompatible or damaged nearest receipt runs
tests again instead of falling back to an older one. Static checks rerun.
The new receipt binds the new tip and records `inherited_test_evidence_from`;
carried first failures remain visible without counting as new recoveries.
Final never inherits tests. Before publishing success, gates re-observe their
input identity and require the workspace to remain clean.

A command shard may declare `workers` (default zero, serial) and
`worker_memory_mb` (default zero, no memory estimate). Before execution the
adapter bounds parallel workers by the declared ceiling, process affinity,
visible ancestor CPU quotas and live available memory, including container
memory headroom. An unaffordable worker or unavailable measurement is an
infrastructure failure. This is a scheduling budget based on declared estimates,
not an operating-system memory limit. Shards execute sequentially, so their
budgets do not overlap within one gate. Allocation is passed as
`SIGNETUM_VALIDATION_WORKERS` and retained under the shard's
`resource_allocation` evidence. Adapters own translating that count to native
tool arguments. The pytest adapter requires xdist for positive allocations;
its failed-node retry remains serial. The engine ceiling is four workers with
a conservative 1024 MiB estimate per worker, configured in `signetum.toml`.

The Python test adapter is `python -m signetum.validation.pytest_runner -- <pytest
arguments>`. Pytest exit 1 with one through thirty explicitly failed nodes may
trigger one serial diagnostic retry. The retry preserves repository pytest
configuration and retains the original phase reports. A passed retry does not
change the original failed exit status. Missing, skipped or collection-failed
nodes never demonstrate recovery. Only a fresh normal validation after a fix
can publish successful evidence.

Gate execution, diagnostics and admission reject a success result carrying
original failure metadata. Historical receipts remain decodable for inspection,
but an ancestor containing recovered failures cannot replace fresh normal
execution. Source-local failure logs retain both attempts, and successful
receipts are not written for failed runs. Legacy recovery-window and threshold
configuration cannot authorize a pass or weaken this first-failure rule.
Each command carries a fresh local owner token while retaining enclosing job
tokens. On normal exit the supervisor inventories its session and token-bearing
detached processes, checks PID birth identity before each signal, and performs
bounded TERM/KILL cleanup. A leak turns an otherwise successful command into a
failure; an already failed command retains its original exit code. Native
observation unavailability blocks success as infrastructure failure. Linux uses
procfs and macOS uses public native process interfaces without application
packages. Timeout, cancellation and the parent-held lease also clean owned
detached descendants before returning or terminating the supervisor.

Each command also registers a private, mode-0700 scratch directory and passes
its path as `SIGNETUM_JOB_SCRATCH`. The registry binds the owner token, device,
inode, canonical path and user; a replaced or shared directory cannot authorize
cleanup. A same-user process whose native cwd is below that exact root remains
identifiable after clearing its environment and detaching from the session.
Similar path prefixes and unrelated directories never qualify. Nested command
roots are below their verified enclosing job root, so caller death does not
lose this ownership channel. Settled jobs remove their scratch; unverifiable
residue is retained and reported rather than deleted by pathname alone.

The pytest adapter places its default temporary directories below the command
root and leaves them available until process settlement. The report plugin
sets basetemp only when pytest has no CLI or repository-configured value;
xdist worker paths and diagnostic attempts remain separate. Explicit project
settings retain precedence. Other language adapters use the same job path
without changing TMPDIR or application runners. Process cleanup uses positive
ownership evidence, rather than inferring ownership from command names or
shared temporary directories; it is not an operating-system isolation boundary.

Each nested check adapter owns an independent process group and deadline. A
supervisor watches a parent-held pipe and terminates its group if its caller
dies, including when an outer deadline kills that caller. Tool identity
and findings commands also run through the bounded command owner; inherited
Git context cannot redirect their repository. Missing tools or unavailable
measurements retain their infrastructure classification when gate failures
are combined.

Delivery
requires the remote target to equal the approved base, derives members and Plan
trailers from the batch's admitted merge commits, constructs an outer merge with the approved base and batch tip as parents without
moving the target, pushes that exact commit without force, and confirms the remote
identity. Only then does it fast-forward the local target and
remove the clean batch worktree and clean member worktrees still at their
admitted commits; a dirty or advanced member is retained and reported. CI may
check these contracts but does not fix, merge, publish, or delete branches.

Human control brackets implementation. The approved change record supplies a
concise view of outcomes, acceptance and autonomy. Consolidated changes retain
significant discoveries and accepted clause edits in their source journal through
`just protocol`; the frozen review binds its committed history and dispositions.
Validation does not append its own success to that source.

Legacy packages retain approved Reviews and Specifications and their existing
common-Git deviation authority at
`signetum/changes/<change-id>/deviations.jsonl`. Linked members and the batch share
that operational state without committing it to the product tree.

The legacy ledger API validates each record or resolution before appending,
under a nonblocking per-change writer lock. Invalid authority, a repeated ID or
an already resolved discovery is refused without changing the ledger; a failed
resolution remains pending and can be corrected through the same API.
Specification resolutions require approved behavior, an approved linked Plan and
accepted required decisions. A deferred target must be a valid specification in
an active change, with its own Review and Plan; a completed Review, withdrawn
specification or arbitrary existing file cannot carry unfinished work. Completed
approved specifications remain usable as behavior authority. Declared change
and decision roots own these checks.

Before final validation, the Agent reconciles every retained discovery into
the applicable Specification, accepted clarifying or superseding Decision,
architecture authority, behavior test, explicit follow-up Change, justified
rejection, or justified no-authority-change result. `final` numbers accepted proposals under the batch lock, then validates the
frozen resulting tip. It refuses unapproved proposals and an unresolved ledger and places approval plus reconciliation data in
the exact final receipt. The Agent projects that data as a delivery review
before explicit delivery. The review is not another tracked authority. Its inputs bind canonical retained
execution records and the bytes of each admitted member receipt. Final rechecks
those inputs after validation before writing a receipt, and delivery rechecks
them before publication; a changed or missing binding requires final again.

The delivery review projects recovered defects from the exact member receipts
named in admission provenance and from the current final receipt, preserving
the source receipt, gate, commit and complete first failure. Missing, altered
or differently bound admitted evidence refuses final; unrelated local receipts
never enter the review.

## Operation results

Lifecycle stdout is one versioned JSON result. The envelope records operation,
status and exit_code, and keeps the business outcome under outcome. Statuses
are passed (0), invalid (2), failed (3), infrastructure_error (4), and conflict
(5). Failure records cause, context, expected recovery and the retained log
path, or null when the repository log authority is unavailable. Check output
and diagnostics go to stderr. Missing tools and unavailable identity inputs
are infrastructure failures; failed checks are validation failures. An open
merge names batch-continue instead of printing a second result.

Final numbers only accepted `ADP-proposal-*` decisions under the batch lock.
Accepted stable filenames and historical decision identities remain unchanged.
Numbering preserves existing supersession edges and never changes approval
status. Each numbering commit records exact `Signetum-Decision-Rename` pairs
bound to its batch base. Review projects recorded resolution targets through
those verified committed identity moves, retaining both original and current
paths without rewriting the ledger. Delivered-commitment normalization consumes
the same mapping rather than inferring moves from rename similarity. A successor uses Partially supersedes for the subset of Supersedes
edges whose unaffected clauses remain authoritative; complete replacements
continue to invalidate current authority citations.

Discoveries are written from the package-owning member branch. A resolution is
written there while the branch is registered; once it has no registered workspace,
a supported resolution may be written from another worktree. Linked worktrees
share the same ledger and change ownership registry under Git common state.

## Workspace operations

The repository owns the delivery branch in .agents/repo-dev/repo.yaml. Runtime
commands remain in signetum.toml. The prepare gate owns dependency preparation;
the batch gate owns admission's static checks. Preparation creates no readiness
receipt and leaves the committed source unchanged. Successful preparation is
reused within the same admission/continuation operation rather than running the
same command again as a static dependency.

| Operation | Observable contract |
| --- | --- |
| workspace-open branch base | Register the exact base before preparation. Retry the same branch/base after preparation failure; refuse a changed base or role. |
| changed [--explain] | Explain the committed contribution and planned member checks without executing shards. It never invokes final or grants readiness evidence. |
| ready | Close a clean implementation member using its recorded base and exact-tip evidence. |
| batch-open --member path [...] | Fix a named batch to the fresh configured delivery base, admit only qualified named members, then prepare and check the merged source. Immutable registration authorizes the batch role; current policy and gates are checked on merged source, not reinterpreted from an older base. |
| batch-admit batch --member path [...] | Capture and merge ready tips, then prepare and run the batch gate. Failure retains the merged state for ordinary fixup/re-admission. |
| batch-continue batch | Prepare the resolved index, run batch static checks, and commit only after success. |
| final | Freeze under the batch lock, number only explicit accepted ADP-proposal identities above batch/base/fresh-remote holdings, reconcile, then validate that exact tip. |
| batch-deliver source target expected-base expected-tip | Publish only the exact validated source, confirm remote identity before moving the target, and apply the shared residue rule. |

The public lifecycle has exactly eight operations above. Explicit local maintenance
uses `signetum maintenance <command>` or `just maintenance <command>`; the
generated runtime provides `.agents/repo-dev/runtime/maintenance.py`. These
commands retain their existing preconditions and authorization boundaries.

| Maintenance command | Observable contract |
| --- | --- |
| workspace-sync [--batch path] | Merge a fresh delivery snapshot or an exact same-repository batch snapshot under its lock; never rewrite the member base. |
| worktree-prepare path | Run the declared prepare gate with its time bounds, without publishing validation evidence. |
| cleanup selector [--protected-worktree path] [--discard] | Fetch the delivery branch and remove only eligible residue selected by worktree, branch, or --all-delivered. |
| batch-discard batch | Remove only a clean unpublished and undelivered batch with no open Git operation. |

Cleanup and delivery share one removal predicate: protect delivery/user-selected
worktrees, keep fresh base-only workspaces, refuse unmerged or advanced tips and
open Git operations, and ordinarily keep dirty state. Explicit cleanup --discard
also permits unstaged and untracked state, but never a changed index. Worktrunk
performs eligible removal in the foreground with hooks disabled; automatic
member readiness never performs cleanup.

A sync conflict remains ordinary member Git state: resolve and commit it,
prepare the resulting environment, then run ready. A batch admission conflict
instead remains open for batch-continue. Neither recovery resets or rebases work.

Consolidated source journals also participate in final and delivery review.
Review inputs bind their exact committed Git blobs, the accepted-history digest
and the source commit. Uncommitted journal suffixes cannot qualify. Current
approved decision transactions must already be present in that history.
Final reconciles discoveries owned by selected changes and older discoveries
affected by their resolutions, retractions or retirements. A pending finding,
missing committed effective evidence or inactive follow-up refuses final.
Retired evidence preserves the old answer and exposes its retirement provenance.
Later, unadmitted member journals do not enter the frozen batch's source review.

The generated review reports the selected standing answers and provenance;
ordinary validation output stays in receipts. Validation appends no success
event to its source. Final rechecks source-journal bindings before writing its
receipt, and delivery rechecks them before publication. Missing or altered
bindings require fresh final validation. The historical local-ledger checks
remain separate while legacy source adoption is still being migrated.

## Repository-owned selection providers

An explicitly declared provider supplies strict source-bound selection through
one owner shared by diagnostics, readiness and admission. The configured runner,
resource allocation, process supervisor and receipt authority remain unchanged.
Inputs and tool identities are rechecked, target arguments bind exact committed
test files, modified test files run whole, and unexplained coverage retains
conservative full-member checks. Existing impact and mandatory checks remain.

Provider code, rules and tools participate in identity. Admission recomputes the
exact selection; inheritance also verifies its explanation of intervening paths.
Final uses the original complete graph and commands. Conflict continuation uses
preparation and batch static checks, without running a selector or another member
test pass against an open merge. Complete final validation judges integration.
Without a provider, readiness executes the full declared member gate and
required checks; changed explains that plan without executing it. Impact rules do not narrow this default or authorize
test inheritance. Final retains its complete gate, including final-only checks.
See [structured selection](../guides/structured-selection.md) for the protocol.


## Explicit development test diagnostics

`just -- protocol test --shard <declared-shard> -- <native-arguments>` appends
explicit runner arguments to one declared command. It preserves existing argv
and targets, uses the same allocator, deadline and owned-process supervisor as
the gate, and writes no readiness receipt. It needs no registered workspace and
can inspect uncommitted development work. The caller owns environment preparation
and required build inputs; there is no hidden sync or build. The engine shortcut
is `just test <paths-or-pytest-options>`; it disables whole-corpus coverage for
explicit diagnostics. Ready and CI retain their full coverage requirement.
CI and release use the same utility for
the tree and world test shards.

Shards remain sequential. Nested jobs respect the enclosing allocation; an
xdist worker is one lane and cannot launch another full allocation. The pytest
adapter records setup/call/teardown totals, slow nodes, elapsed time, reported
child CPU and the OS largest-child RSS observation in diagnostic output.
Largest-child RSS is not a whole-worker process-tree peak and cannot justify a
new memory reserve. Allocation and shard elapsed time use existing details.
Failed-node diagnostic retries remain serial and preserve the first failure.
These observations create no timing or test-count threshold.

Core tests cover pure matrices once. Real repository tests retain source,
authority, locking, atomicity, failure and cleanup boundaries. Portable and
installed tests retain representative independent execution and adapter-specific
failures. Test setup provisions remotes only when used; successful installed
wheel payloads may be read by several consumers in a worker, while mutable
consumer state and generated outputs remain private. Failed setup is not cached.

`changed` is selection-only and never starts a shard. Explicit feedback uses the
existing diagnostic owner, and ready creates member evidence. `protocol status`
derives workspace, change, findings and source-current recorded receipt views
without checks or network access. It does not observe current tool identities or
re-run a provider, so admission retains qualification authority. There is no
second status store. Utility refusals share the operation result/exit contract.

Optional Python reach produces the existing selection response without importing
source. Consumer families and dynamic loader declarations remain bound inputs.
Unknown data or dynamic reach falls back, and modified tests retain whole-file
coverage. Weighted scheduling preserves every scheduling unit; hints cannot
change membership. Partition rules name roots, patterns, binding and shared groups
as validation inputs. Plans bind source, graph, commands and observed tools.
Run uses the supervised adapter; combine requires exactly one passing result per
partition and rejects overlap or stale identity. This is CI diagnostic evidence,
not a lifecycle final receipt. Preparation stays explicit and final stays complete.

Final retains accepted stable decision filenames. Optional explicit proposal
numbering refuses before mutation if it would rewrite a consolidated approval
or source journal. Numeric allocation is not a routine development document step.

Change scope is discovered from current change records, Reviews and the declared
specification pattern at either the base or reviewed tip. Retained raw historical
documents do not become executable approval packages merely by occupying a
change directory. Removing a current authority remains in scope; malformed
current authorities still refuse qualification. No YAML approval fallback exists.

Hosted CI and release invoke `protocol test --gate final` through one local
composite action. It runs strict declared dependency order without workspace
registration, member selection, inheritance or lifecycle receipts. Single-shard
diagnostics retain native arguments; gate diagnostics reject them. `mise.toml`
owns native acceptance tools. CI covers host Python 3.12 and 3.13; failed output
is retained for seven days with a bounded terminal preview. Composite actions
share workflow checks for exact external action identities and checkout source.
