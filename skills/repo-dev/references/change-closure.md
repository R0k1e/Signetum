# Change closure

Read this reference for any governed requirement, Specification, Plan,
dispatch, completion claim, deferral, reopening, or supersession.

## Establish ownership

Resolve all authority locations and schemas through the repository manifest.
Read the affected atomic Review clauses before drafting or changing a
Specification. Every active clause must have exactly one current approved
Specification owner. Approved exclusions are Review decisions, not omissions.

An approved Specification is the behavior authority. Its contracts,
invariants, negative cases, and boundaries remain in scope until satisfied,
transferred, or superseded through the repository's approved process.

## Prove Plan coverage

Before approving or executing a Plan, map every obligation owned by its
Specification to an explicit Plan obligation and acceptance evidence. Fail
closure for missing, duplicate, ambiguous, or unresolved coverage.

A dispatch brief may select a subset of Plan obligations for one worker or
stage. It does not amend the Plan or Specification. After a partial dispatch,
report the selected obligations complete only when evidence supports them and
leave the Plan open for every remaining obligation.

Do not accept prose status, an agent report, a passing member gate, or a branch
name as proof that requirements are exhausted. Use the repository's declared
traceability and evidence authorities.

## Defer without losing scope

Deferral is valid only after the affected Review clause is transferred to
another approved Specification with unambiguous current ownership. Record the
relationship required by the repository schema, then recompute coverage. If no
approved receiving owner exists, stop: the current Plan remains open.

## Preserve history

Never rewrite accepted Review, Specification, Plan, delivery, or acceptance
history to describe later intent.

- A new requirement creates a new Review clause and follows normal ownership.
- A changed accepted behavior creates a new clause and superseding contract.
- An implementation defect follows the repository's defect/reopen authority
  without pretending the accepted contract changed.
- A discovered omitted requirement reopens the affected Review or creates the
  repository-declared successor, preserving the original delivery and
  acceptance record.
- Human rejection after delivery records rejection and reopen/supersession; it
  does not erase delivery.

Recompute parent status from clause states. A parent cannot be more complete
than its least-complete clause.
