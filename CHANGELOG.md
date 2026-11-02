# Changelog

This file records user-visible Signetum releases. Earlier RepoSeal entries retain
their original release history. Git and accepted change records retain reasoning.

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
