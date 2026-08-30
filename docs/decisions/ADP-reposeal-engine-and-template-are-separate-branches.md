# RepoSeal engine and Template are separate branches

Status: Accepted
Review date: 2026-08-30
Supersedes: ADP-foundation-is-a-standalone-template.md
Superseded by: None

## Context

RepoSeal 2.0 used one default-branch tree as its engine source, governance
history, release project, public homepage, and GitHub Template. A copied
repository therefore inherited RepoSeal's Python package, tests, schemas,
profiles, editor adapters, historical changes, product decisions, and release
workflows before it could contain the user's product. Hiding those files would
not remove the ownership conflict.

## Decision

The `engine` branch owns RepoSeal implementation, tests, schemas, profiles,
skills, decisions, changes, release automation, and the canonical Template
source under `template/`. The default `main` branch is a deterministic rendered
artifact containing only the clone-ready Template and product entry points.

The `reposeal` package owns executable lifecycle and validation behavior. The
Template pins one exact immutable package version and does not vendor engine
source or reserve application roots. A rendered `main` is never hand-edited;
promotion follows a successful engine release and clean-room Template gate.

Repositories created from the Template remain independent. A later package
version is adopted as an ordinary local governed change, never synchronized
automatically.

## Consequences

- `git clone` and GitHub Template creation produce the same clean user surface.
- RepoSeal's own Plans and decisions never enter newly created repositories.
- Engine development uses `engine` as its approved base rather than `main`.
- Publishing the package is a prerequisite for promoting a Template version.
- The release authority must validate both engine source and rendered Template.
