# Development lifecycle concepts

RepoSeal separates authorities so that a green branch cannot conceal an
unrecorded requirement or silently redefine requested behavior.

| Artifact | Owns | Does not own |
| --- | --- | --- |
| Review | Human source, atomic clauses, exclusion, delivered acceptance, rejection, reopening | Technical behavior or implementation order |
| Specification | Observable input/output behavior, boundaries, invariants, negative contracts, structured deferral | Handwritten completion or delivery state |
| Decision | Why an architecture, process, or security choice is valid | Current implementation facts or task sequencing |
| Plan | One implementation path, approved base, exhaustive obligations, evidence and file boundaries | Requirement meaning or reduced scope |
| Member receipt | Validation of one exact member commit | Batch integration, delivery, or human acceptance |
| Final receipt | Complete validation of one exact frozen batch tip | Permission to deliver |
| Delivery result | Members, Plans, batch identity, target identity, remote confirmation, cleanup | Human acceptance |
| Architecture | How the currently delivered system works | Pending behavior or historical rationale |

## Requirement coverage

Every active, non-excluded Review clause has exactly one current approved
Specification owner. Every owned clause appears in at least one Plan obligation.
A deferred clause first transfers to another approved Specification; prose such
as “later” or “deliberately absent” does not close it.

This proves coverage for recorded clauses. It does not prove that the original
human statement was interpreted correctly, so Specification approval and
post-delivery acceptance remain human decisions.

## Repository comprehension

An Agent begins at the architecture entry, follows responsibility documents,
loads mandatory and path/intent-selected policy, and searches production and
test implementations before proposing a change. It emits the selected policy
groups and reasons so routing is inspectable.

That manifest proves routing occurred; it is not proof of comprehension. Plans
therefore also record current authorities, public behavior evidence, reuse
judgment, positive and negative contracts, a through-case, and adversarial
checks.

## Quality evidence

- Unit tests protect pure contracts, state transitions, and data matrices.
- Property tests explore valid and invalid input spaces.
- Integration tests traverse a real public boundary and its production path.
- Contract tests keep schemas, generated clients, packages, and public commands aligned.
- Regression tests reproduce a reported bug at its observable boundary.

Tests do not freeze private call order, incidental fields, helper names, or
temporary implementation structure. Coverage is supporting evidence, not a
substitute for testing the promised behavior.

## Derived states

Ready, integrated, delivered, accepted, reopened, and excluded are different
states derived from different evidence. A parent change is no more complete
than its least-complete active clause.
