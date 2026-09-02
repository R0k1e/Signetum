# Why Signetum exists

Coding Agents can write code quickly, but repository delivery fails for reasons
that code generation alone does not solve: a requirement stays in chat, an
Agent misses an existing authority, parallel sessions overwrite one another,
every branch repeats expensive tests, or a green commit cannot explain what was
actually delivered.

Signetum makes the repository itself carry the answer. It seals each recorded
requirement to explicit design, isolated implementation, behavior evidence, and
an inspectable delivery instead of letting those obligations disappear in chat.

## Requirement coverage is a relation, not a checklist

A Review preserves atomic human clauses. Exactly one approved Specification
owns each active clause, and its Plan maps every clause to implementation and
evidence. A postponed clause must transfer to another approved Specification.
This makes recorded coverage machine-checkable without claiming perfect
natural-language interpretation.

## Repository comprehension starts from evidence

The architecture map, repository manifest, focused policy, production search,
and public behavior tests identify existing authorities before a Plan proposes
changes. An inspectable routing manifest shows what the Agent loaded and why;
the Plan must still demonstrate concrete understanding through authority, reuse,
contract, and adversarial analysis.

## Parallelism ends at one controlled batch

Agent Team members work in isolated, Plan-owned worktrees. Each member closes
against its exact commit. A batch admits only explicitly named members, runs the
complete gate once on the frozen combined tree, and delivers only that validated
identity. This reduces repeated full-suite work without weakening the final
contract.

## Delivery remains reviewable after the chat is gone

The machine-readable delivery result records requirements, Plans, original and
integrated commits, the validated batch tip, the delivery commit, remote
confirmation, and cleanup. Human acceptance remains a later, explicit state.

## What Signetum is not

Signetum is not an Agent runtime, project-management service, hosted CI
product, or guarantee of defect-free software. It is a standalone GitHub
Template for repositories that want an inspectable Agent development lifecycle.
