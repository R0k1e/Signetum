# ADP: Compatible Skill updates stay outside projects

Status: Accepted
Human approval recorded: 2026-11-01. The owner approved removing implementation pins and delivering explicit updates and cleanup.
Supersedes: None
Superseded by: None

## Decision

Current project bindings describe supported configuration/protocol contracts and
project commands, not an engine implementation hash. Manifest format five removes
engine_digest; that one-time format migration is explicit. Actual engine and
dependency identities stay bound to each validation observation and receipt.
A new runtime does not inherit success from old-runtime evidence.

The installed Skill owns explicit read-only checking and installation upgrades.
An upgrade verifies the complete candidate and its isolated environment before
switching a stable entry, refuses active-use replacement and retains old usable
versions. It never edits a project. Incompatible project contracts require a
separate reviewed adoption; network or release absence cannot claim up-to-date.
Ordinary operations remain offline with respect to Skill distribution.

The previous exact implementation pin made every compatible tool repair require
a project commit. Retaining or silently ignoring that pin would preserve the
coupling or conceal the contract change. This replaces that choice for current
bindings while retaining original historical authorities and runtime-integrity
checks. Read-only assistance does not enter the development approval lifecycle.
