# Changelog

This file records user-visible RepoSeal releases. Git history and delivered
Plans retain detailed implementation provenance.

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
