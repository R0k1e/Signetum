# One TOML authority owns repository configuration and validation commands

Status: Proposed
Review date: 2026-08-31
Supersedes: ADP-runtime-and-agent-routing-are-separate.md, ADP-template-runtime-is-self-contained.md
Superseded by: None

## Context

The language-neutral execution decision and its approved Specification say
`reposeal.toml` is the sole active configuration authority. Later decisions
placed executable runtime commands in a second `reposeal.yaml` file, whose
contents are JSON. A fresh Template therefore exposes two product
configuration files and can declare profiles in one without executing their
checks in the other.

## Decision

`reposeal.toml` owns RepoSeal identity, profiles, repository bindings, impact
rules, and strict member/final argv arrays. The copied lifecycle reads the same
versioned file with Python's standard-library `tomllib` and executes commands
through Mise without a shell.

`.agents/repo-dev/repo.yaml` remains a separate Agent policy-routing authority;
it is not product runtime configuration. The copied runtime remains
self-contained and does not install or import the RepoSeal distribution.

`reposeal.yaml` is deleted. There is no alias, fallback parser, dual-read
period, or automatic migration channel for repositories already created from
an older Template.

## Consequences

- A repository has one visible RepoSeal product configuration.
- Validation declarations and their execution cannot drift between files.
- Agent routing remains separate because it serves a different consumer and
  responsibility.
- Existing copied repositories adopt the change manually as an ordinary
  governed change.
