# The development foundation is a standalone GitHub Template

Status: Accepted
Review date: 2026-08-30
Supersedes: ADP-template-becomes-versioned-development-foundation.md
Superseded by: None

## Decision

This repository remains internally complete but is distributed as a one-time
GitHub Template. Repositories created from it do not retain an upgrade,
dependency, skill-sync, subtree, or merge relationship with this repository.

Each generated repository owns and may customize its copied lifecycle. Later
improvements may be implemented manually in another repository as an ordinary
local Review, Specification, Plan, implementation, validation, and delivery.

## Consequences

The package and release workflow validate this template itself; they are not a
cross-repository update protocol. No compatibility manifest promises that an
existing repository can consume a later template revision automatically.
