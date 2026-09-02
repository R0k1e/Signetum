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

A member gate judges what the member owns. A judgement over the whole tree or a
whole corpus belongs to the final gate, because a member owns neither the
finding nor, while its base is frozen, any means of acquiring the fix. A check
enters a member gate only when it accepts a scope, or when it reports findings
as a comparable set so the gate can judge the member tree against the same
check run on the member's base. A check that does neither is a final-gate
check.

Member evidence can establish **ready** only. Integration evidence establishes
**integrated** only for the named integration identity. Neither proves delivery
or human acceptance. Agent summaries are explanations, never evidence.

## Test what the contract owes

Do not assert that a string literal is absent. `assert "widget" not in payload`
records the change its author was making, not a behavior the code owes anyone:
it is true when written and afterwards only constrains renaming, and it silently
stops protecting anything the author did not think to list. Assert what is
there. Where absence really is the contract, bind the value to a name which says
why it must not appear, or state a relation between two observations, so the
assertion keeps holding for cases nobody enumerated. Never repair such an
assertion by rewriting it as an equality on the same object: that pins an
internal shape and breaks on any legitimate addition.

Keep disposable test output separate from durable specifications, plans,
receipts, and delivery state. Leave a coherent, clean, validated member ready
for explicit integration or delivery authorization.
