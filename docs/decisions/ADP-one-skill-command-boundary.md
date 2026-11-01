# ADP: One Skill command boundary

Status: Accepted
Human approval recorded: 2026-11-01. The owner approved the complete simplification plan and delivery.
Supersedes: None
Superseded by: None

## Decision

One engine command registry owns public dispatch and help. The installed launcher
only prepares/verifies its isolated environment and forwards arguments. Eight
lifecycle operations stay direct; change and test utilities have semantic groups.
There are no public lifecycle/protocol or duplicate validation aliases.

The root repository owns site, release and product-surface tools. They are moved,
not copied, outside the distributed Skill. Generic project checks remain runtime
capabilities. Full Skill content identity is separate from the project engine pin;
explicit updates verify both and migrate project bindings only when necessary.

The observed advertised-command refusal came from duplicated dispatch ownership.
Retaining aliases would preserve this ambiguity. Current instructions describe
owners once; historical contracts and decision evidence remain immutable. Cheap
static failures block expensive repository tests, while successful final checks
retain completeness and first-failure/process-settlement semantics.
