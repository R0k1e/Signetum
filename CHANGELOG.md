# Changelog

This file records user-visible Signetum releases. Earlier RepoSeal entries retain
their original release history. Git and accepted change records retain reasoning.

## 0.3.4 (unreleased)

An open batch takes a sibling's delivery without being reopened, and concurrent
decision clause identities are refused before they are integrated.

- `maintenance workspace-sync` run in an open batch merges the fresh delivery tip
  as a merge commit and advances the recorded batch base to it. Admitted members
  stay admitted with their ready receipts and plans, the batch gate runs over the
  merged commits, and `final` and `batch-deliver` then bind the new base. A
  conflict stays open for `batch-continue`. Delivery history that does not descend
  from the batch base, or `--batch` named from a batch, is refused.
- `batch-admit` and batch synchronization refuse when two different changes write
  one decision clause ID, naming the clause, both changes and their workspaces.
- `batch-deliver` onto a delivery branch that moved names batch synchronization
  as the recovery.

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
