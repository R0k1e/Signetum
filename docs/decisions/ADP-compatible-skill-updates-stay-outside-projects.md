# ADP: Compatible Skill updates stay outside projects

Status: Accepted
Human approval recorded: 2026-11-01. The owner approved removing implementation pins and delivering explicit updates and cleanup.
Supersedes: None
Superseded by: None

## Decision

Current project bindings describe supported configuration/protocol contracts and
project commands, not an engine implementation hash. Manifest format five removes
engine_digest; that one-time format migration is explicit and stays format five.
Omitted evidence fields mean the published evidence protocol and the published
schema digest. An explicit digest must equal that schema. Actual engine and
dependency identities stay bound to each validation observation and receipt.
A new runtime does not inherit success from old-runtime evidence.

The installed Skill owns a read-only check and installation upgrades. Bare update
installs the newest eligible stable release and prepares that candidate. `--check`
and `--to` remain optional. An upgrade verifies the complete candidate and its
isolated environment before switching the install entry. Version directories stay
immutable. A running command keeps the directory it already resolved; switching
the entry does not take that directory's use lock. The updater refuses to
overwrite a Git-managed source directory or rewrite version storage. It never
edits a project. An already-current or older stable release does not replace the
installation. Incompatible project contracts require a separate reviewed adoption.
Network or release absence cannot claim up-to-date and leaves the old entry usable.
Commands other than update remain offline with respect to Skill distribution.

The previous exact implementation pin made every compatible tool repair require
a project commit. Retaining or silently ignoring that pin would preserve the
coupling or conceal the contract change. This replaces that choice for current
bindings while retaining original historical authorities and runtime-integrity
checks. Read-only assistance does not enter the development approval lifecycle.
