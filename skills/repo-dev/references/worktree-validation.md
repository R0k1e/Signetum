# Worktree and validation

Read this reference for implementation, member readiness, validation evidence,
or final-gate work.

## Isolate implementation

Use the workspace authority, base identity, and environment command declared by
the repository manifest. Work only in the Plan-owned workspace. Preserve
unrelated changes and stop when the declared base, skill identity, schema, or
workspace invariant does not match.

Search production and test authorities selected by architecture and manifest
before changing an implementation. Reuse or extend the owning authority and
remove superseded duplicate behavior. For defects, reproduce the failure
through its public boundary before changing production code. For new behavior,
write contract-protecting tests before implementation.

## Bind evidence

Run targeted or changed validation during coherent work and the repository's
complete final authority once on the frozen integration tree. Use only declared
selectors and commands; do not invent a runner or copy its selection logic.

Evidence must identify the exact source or integration identity, declared tool
and skill identity, selected scope, result, and any repository-required inputs.
A diagnostic may say complete validation is required but must not silently run
or claim that gate.

Member evidence can establish **ready** only. Integration evidence establishes
**integrated** only for the named integration identity. Neither proves delivery
or human acceptance. Agent summaries are explanations, never evidence.

Keep disposable test output separate from durable specifications, plans,
receipts, and delivery state. Leave a coherent, clean, validated member ready
for explicit integration or delivery authorization.
