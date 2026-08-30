# The Template runtime is self-contained

Status: Accepted
Review date: 2026-08-30
Supersedes: ADP-reposeal-engine-and-template-are-separate-branches.md
Superseded by: None

## Decision

The rendered Template carries the minimal standard-library lifecycle runtime
required by its eight public operations. It does not install, import, or pin
the RepoSeal distribution. Repository validation is an explicit list of argv
commands in `reposeal.yaml`; the runtime executes those commands without a
shell.

The `engine` branch remains the development and provenance authority for the
runtime, tests, schemas, and release tooling. Rendering copies the reviewed
runtime into `main`. A repository created from the Template owns that copy and
evolves independently; RepoSeal releases are not an upgrade channel.

## Consequences

- A clone remains usable if PyPI, RepoSeal releases, or this repository vanish.
- The public Template contains one small runtime implementation but no engine
  tests, schemas, profiles, skills, plans, decisions, or release automation.
- Runtime improvements reach future Template renders only; existing repositories
  adopt them manually as ordinary governed changes.
