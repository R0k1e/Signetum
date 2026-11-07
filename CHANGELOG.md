# Changelog

This file records user-visible Signetum releases. Earlier RepoSeal entries retain
their original release history. Git and accepted change records retain reasoning.

## 0.3.4 (unreleased)

Every workspace ends delivered, contained or abandoned, and only that proof
removes it. An open batch takes a sibling's delivery without being reopened, and
concurrent decision clause identities are refused before they are integrated.

- Contained: a clean workspace whose commits outside the delivery branch are all
  patch-equivalent to delivery commits, with no merge resolution of its own, or
  whose changed paths all have the same content in the delivery branch. Cleanup
  removes it like a delivered one, including a batch left over after its members
  landed through another batch.
- `batch-deliver` now sweeps every registered workspace after publication, not
  only the delivered members, and `maintenance cleanup --all-delivered` runs the
  same sweep. Dirty, fresh, mid-operation and uncontained workspaces stay with a
  reason. `--discard` requires a selected worktree or branch.
- `maintenance workspace-abandon <worktree> <confirmed-tip> --actor --source
  --reason [--discard]` removes undelivered work only with the owner's
  confirmation of that exact full commit. It refuses delivered or contained
  workspaces. `maintenance batch-discard` is removed; abandon replaces it.
- Cleanup and delivery results list each removed workspace with its branch, tip,
  outcome and proof instead of a bare path. Each removal writes a retirement
  record under the Git common directory's `signetum/retired`.
- `status` lists every registered workspace with the outcome it proves against
  the last fetched delivery branch, or the reason it stays.
- `maintenance workspace-sync` run in an open batch merges the fresh delivery tip
  as a merge commit and advances the recorded batch base to it. Admitted members
  stay admitted with their ready receipts and plans, the batch gate runs over the
  merged commits, and `final` and `batch-deliver` then bind the new base. A
  conflict stays open for `batch-continue`. Delivery history that does not descend
  from the batch base, or `--batch` named from a batch, is refused.
- `batch-admit` and batch synchronization refuse when two different changes write
  one decision clause ID, naming the clause, both changes and their workspaces.
- A member that synchronized delivered change records no longer claims their
  decision clauses at admission, so a batch sibling may amend those clauses.
- `batch-deliver` onto a delivery branch that moved names batch synchronization
  as the recovery.
- A member that changes the engine or the manifest schema no longer strands its
  ready siblings. `batch-admit` run with the batch's engine accepts a sibling's
  ready receipt produced by an older engine without rerunning its checks, as long
  as the sibling's own inputs are unchanged; the batch gate then runs over the
  merged result. An engine that cannot read a newer manifest names this path
  instead of reporting only an unknown field.
- Member ratchets measure their baseline in a checkout prepared by the declared
  prepare gate, so a baseline command that needs the project environment runs.
  A baseline that cannot be measured now fails the shard with its cause instead
  of passing against an empty baseline; `baseline_unavailable` is removed from
  the ratchet details.
- Stacked members split one large change into a chain delivered through one
  batch. `workspace-open <branch> <parent-branch>` bases a member on another open
  member's tip and records that parent; its `ready` selects only its own diff.
  In a stacked member, `maintenance workspace-sync` merges the parent's later
  commits until the parent is delivered, and `ready` and admission refuse until it
  does. `batch-admit` requires the parent admitted first at the exact tip the child
  holds. The final review names each member's parent, and the `status` next action
  names the needed sync or the admission order.
- Breaking: `changed` is removed; the lifecycle has seven operations. `ready` is
  the development loop (commit, ready, fix, ready), and `ready --explain` shows its
  selection without running checks.
- Admission and `batch-continue` run only the declared batch gate, which may run
  no integration check; they no longer refuse a gate that does not run the member
  shards an increment selects. Final stays complete, so cross-member failures
  surface there.
- Breaking: the shard field `covers` is removed; a manifest that declares it is
  refused at load. Delete it from `signetum.toml`.
- A defect that appears only when members combine may be fixed by commits made
  directly in the batch under the batch's own approved change record. Final
  attributes each such commit in the review and refuses an unattributed direct
  implementation commit; after a failed final, `status` names both repairs.
- Recording a decision no longer costs a validation round. A commit that changes
  only change records, keeping every contract digest, keeps the member's ready
  evidence: `ready` runs source admission and no check, and admission, `status`
  and final accept the earlier receipt. A records-only batch increment runs no
  batch gate check. In test inheritance a change-record path affects no shard.
- `change record`, `resolve`, `retract` and `retire` work in a batch for the
  changes it integrates, without claiming them; final attributes such record-only
  batch commits to those changes.
- Breaking: `change resolve --disposition deferred` needs only a reason; the
  follow-up requirement and its approved transfer are no longer required. An
  optional `--followup change-id[#REQ-ID]` may name an approved change on any
  local branch and is judged only when written. The final review lists every
  deferred item in a top-level `unfinished_work`.
- Resolution evidence may also name a machine-local validation receipt.

Signetum ships as one plugin for Claude Code and Codex: the Skill plus a command
guard, installed and updated by the host plugin managers.

- Install with `claude plugin marketplace add R0k1e/Signetum` and
  `claude plugin install signetum@signetum`, or `codex plugin marketplace add
  R0k1e/Signetum` and `codex plugin add signetum@signetum`. The Skill is now
  `signetum:signetum`. Remove an earlier standalone copy in
  `~/.claude/skills/signetum` or `~/.codex/skills/signetum`, or both Skills stay
  listed, and review the plugin hook in Codex at its next start.
- The plugin's Bash PreToolUse guard refuses stash, destructive reset, restore,
  clean and checkout, forced checkout or switch, force push including
  `--force-with-lease`, unbounded `rm -rf`, any `git merge` or `rebase`,
  `wt step rebase|push`, `wt merge`, ad-hoc `git worktree add|move|remove`,
  `wt remove`, `wt switch --create`, `git branch -D` and pre-commit on a tree with
  unstaged changes, and names the Signetum operation to use. Quoted mentions and
  read-only Git pass. A guard that cannot run allows the command.
- Adoption also enables the plugin at project scope in `.claude/settings.json`
  and `.codex/config.toml`, so the guard follows adopted repositories.
- The engine environment moves to `~/.local/share/signetum/runtime/<fingerprint>`
  and is shared by every installed copy; run `setup` once after installing the
  plugin.
- `update` checks the release pinned in the marketplace against the project and
  upgrades each host through its plugin manager. `update --to`, `update --source`,
  version directories and entry switching are removed.
- Other agent tools, such as OpenClaw, Grok, Gemini CLI or Cursor, install the
  same Skill folder as a plain Skill from `signetum-skill-<version>.zip`, without
  the guard; Claude Code and Codex users install only the plugin. Receipts and
  `batch-deliver` still carry the protocol guarantees without the guard. `update`
  on a plain Skill replaces the folder in place after the same compatibility
  check, runs no host command and refuses a folder inside a Git work tree;
  results report `install` as `plugin` or `plain`.

A long validation round loses less work: owed nodes run first, unrun nodes stay
owed, and one failing check no longer hides the others.

- Breaking: `SIGNETUM_NODE_REPORT` is removed. A runner that reports node
  outcomes must declare `{signetum.node_report_file}` as a whole argument of its
  shard command; the packaged pytest runner takes it as
  `--node-report {signetum.node_report_file}` before `--`. The report keeps
  `{"failed": [...], "passed": [...]}` and may add `"unreached": [...]`, read even
  after the shard's time bound. Unreached entries fail the gate, the result
  reports their count, and the next gate owes them.
- `{signetum.priority_nodes_file}` is replaced by a file,
  `{"schema_version": 1, "nodes": [...]}`, listing the entries that shard owes
  from an earlier failed gate, to run first. Unknown `{signetum.*}` arguments are
  refused.
- `after = [...]` on a shard orders it after other shards without skipping it
  when they fail, so one round reports every failure. `requires` still gates.
- `ready` inherits test evidence per shard. Impact rules decide, with or without
  a selection provider, which `inherit = true` shards the paths changed since
  the previous ready affect; each unaffected shard reuses that ready's passing
  evidence and the affected ones rerun. A modified test file reruns only the
  shards its rules name. A path no rule explains still reruns every shard, and
  final, batch admission and continuation never inherit.
- `after` no longer adds its prerequisite to a gate: it only orders shards the
  gate already runs. `requires` prerequisites still run with their dependents.
- When no implementation commit follows the latest approval, `ready` refuses
  naming the approval commit, and its expected action and the `status` next
  action give the remedy.

Every engine value now reaches a runner through a declared command placeholder.

- Breaking: `SIGNETUM_BASE`, `SIGNETUM_RATCHET_BASELINE`,
  `SIGNETUM_CONTRIBUTION_PATHS`, `SIGNETUM_ADMISSION_BASE`,
  `SIGNETUM_VALIDATION_WORKERS`, `SIGNETUM_RECOVERY_REPORT` and
  `SIGNETUM_SCHEDULE_FILE` are removed. A shard that needs one must declare
  `{signetum.base}`, `{signetum.ratchet_baseline}`,
  `{signetum.contribution_paths_file}` (a file holding
  `{"schema_version": 1, "paths": [...]}`), `{signetum.admission_base}`,
  `{signetum.validation_workers}` or `{signetum.recovery_report_file}` as a whole
  command argument. Range values outside the member and batch gates, and the
  admission base outside a batch gate, are explicit empty arguments.
- Breaking: the scheduling weights file is the `[validation] schedule_file`
  setting, which must be listed in `repository.lockfiles`, and reaches a runner as
  `{signetum.schedule_file}`. Declaring that placeholder without the setting is
  refused.
- Breaking: the packaged pytest runner takes `--recovery-report`, `--workers` and
  `--schedule-file` before `--`, next to `--node-report`; repositories using it
  must declare `--workers {signetum.validation_workers}` and
  `--recovery-report {signetum.recovery_report_file}` to keep worker allocation
  and retry recovery evidence.
- A ratchet command may declare `{signetum.validation_workers}`; no other
  placeholder. An engine run inside an outer pytest-xdist worker still runs one
  lane.

## 0.3.3

Batch gates can declare which member shards they stand for, and a recorded root
cause releases one remembered failed node.

- A validation shard may declare `covers = ["<shard>", ...]`: the shards whose
  selected checks it executes for its own range. Batch admission accepts a
  selected shard when a batch-gate shard covers it, directly or transitively.
  Manifest load rejects covers that name an undeclared shard, the shard itself,
  a world shard, a world covering shard, or a cycle.
- A remembered failed node is released when a change record observation of the
  workspace names it as evidence with its root cause, even when its shard stays
  selected. Without that record it must report passing in the next run. A
  retry-only pass still never offsets a first failure.

## 0.3.2

Declared commands use one Mise resolver, and ready qualifies the committed tree.
The release is a candidate until published.

- Preparation, tool identity, shard commands, findings commands, and ratchet
  diagnostics run through `mise exec --`. Repository Git context and foreign
  Python environments are removed. The Skill engine environment is not prepended
  onto application PATH.
- `ready` prepares and checks a temporary detached checkout of the member commit.
  The editing worktree stays. The result shows each carried approval's actor,
  date, source, and contract digest.
- `adopt inspect` reports tool versions, the Git 2.7 and 2.17 floors, and PATH
  uv beside `mise exec -- uv`. A difference does not fail inspection.
- `update --check` can send a GitHub token without printing it. A rate limit
  stays unavailable and names `update --source`.
- `batch-deliver` states that source and target are worktree directories and the
  last two arguments are full commits.
- A repeated adopt preview names the existing file. `change open` without a
  member workspace names `workspace-open`.
- A manual merge or a copied `Signetum-Sync:` trailer still does not move the
  ratchet baseline. A failed ratchet now lists those merges and names
  `maintenance workspace-sync` and `maintenance workspace-sync --batch`. Member
  gate shards receive `SIGNETUM_BASE` and `SIGNETUM_RATCHET_BASELINE`, and the
  member receipt binds both.
- Workspace listing ignores detached checkouts, so a concurrent `ready` no
  longer makes `workspace-open`, `batch-open`, and cleanup refuse the listing.
- `batch-admit` and `batch-continue` select checks over the commits added since
  the batch's last passing gate. The batch gate must cover the member shards that
  selection requires, the complete member gate without a provider, or the
  operation refuses before checks run. One admission of several members is one
  range, and batch shards receive its start as `SIGNETUM_ADMISSION_BASE`. A
  documentation-only admission that selects nothing still passes. Signetum's own
  batch gate is now its member gate.
- A failed member, batch, or final gate writes a failure receipt under the Git
  common directory's `signetum/failures`. It names the workspace, changes, tip,
  first-attempt failed nodes, and nodes that passed only on retry. Runners report
  nodes through `SIGNETUM_NODE_REPORT`; the packaged pytest runner does.
- Before running checks, the next gate in that workspace refuses and lists each
  remembered node that is neither selected again nor named with its root cause by
  a `change record --evidence <node-id>` observation. A reselected node must pass
  in that run. A retry success still never offsets a first failure.

## 0.3.1

Signetum's own Git commands use spellings available since Git 2.7. The release
is a candidate until published.

- Discover the primary worktree from blank-line `git worktree list --porcelain`
  and resolve relative Git paths without newer rev-parse or branch options.
- Signetum's own commands need Git 2.7 or newer. Worktrunk stays at 0.74.
  Cleanup through Worktrunk needs Git 2.17. Worktrunk 0.75 or newer needs Git 2.43.

## 0.3.0

Signetum is a standard Skill for reliable Agent development and delivery, from a
single Agent across sessions to parallel work in evolving repositories.

- Install one complete Skill with its own locked execution environment. Review
  project bindings while retaining application tools, dependencies and entry files.
- Keep approved outcomes, significant decision history and a concise derived
  decision set so later sessions can continue without repeating decisions.
- Develop in isolated worktrees, integrate named changes and explicitly deliver
  the exact checked source using readable branches and commit subjects.
- Run existing project checks, preserve first failures and settle owned processes.
  Optional selectors, weighted scheduling and CI partitions retain complete final checks.
- Start through the bilingual homepage and one installation/adoption guide.

### Updating from RepoSeal

This release replaces the template and copied runtime with the `signetum` Skill.
It uses manifest schema 5 and protocol 2; projects declare compatibility instead of an engine code hash. Existing projects require an explicit
reviewed adoption; installing the Skill does not update them automatically.
Historical tags remain unchanged. The release is a candidate until published.

## 0.1.0 - 2026-08-30

- Start the public Template version line without rewriting the historical v2
  and v3 architecture tags.
- Use self-contained TOML Review and Specification contracts.
- Enforce Review-to-Specification-to-Plan ownership in member and final gates.
- Align the copied repository's delivery branch with GitHub's `main` default.

## 3.0.0 - 2026-08-30

- Separate the RepoSeal engine branch from the rendered default-branch Template.
- Rename the distribution, import package, manifest identity, CLI, receipts,
  and profile authority to `reposeal` without compatibility aliases.
- Add a deterministic, minimal Template with equivalent English and Simplified
  Chinese entry points and no engine, editor, or maintainer residue.
- Package the eight lifecycle operations so cloned repositories pin one exact
  released RepoSeal version instead of vendoring engine code.

## 2.0.0 - 2026-08-30

- Launch RepoSeal as an Agent-native, standalone GitHub Template.
- Establish “Seal every change with evidence” as the public product position
  with one canonical seal-and-repository visual identity.
- Document the complete Review-to-acceptance lifecycle, Agent Team batch
  delivery, behavior-oriented testing, and customization boundaries.
- Introduced typed repository manifests, profiles, and the check-only CLI.
- Added Review, Specification, Plan, evidence, delivery, acceptance, and reopening traceability.
- Added isolated workspaces, named batch assembly, frozen final validation, and explicit delivery.
