# Mise and Worktrunk are execution authorities

Status: Accepted
Review date: 2026-08-30
Supersedes: None
Superseded by: None

## Decision

Mise owns external tool installation, versions, and command projection.
Language ecosystems retain their own locked dependencies. Worktrunk is the
single backend for workspace creation, discovery, and removal; RepoSeal owns
the policy deciding when those actions are allowed.

The copied runtime remains self-contained and repository-owned. It invokes the
pinned authorities but never installs or imports the RepoSeal distribution.

## Consequences

- Git and Mise are the only host prerequisites for the default Template.
- Hand-written worktree creation and cleanup paths are removed when replaced.
- A missing or incompatible tool fails with an actionable preflight diagnostic.
