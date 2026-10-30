# Development lifecycle concepts

Signetum separates authorities so that a green branch cannot conceal an
unrecorded requirement or silently redefine requested behavior.

| Artifact | Owns | Does not own |
| --- | --- | --- |
| Change record | Intent, stable requirements, acceptance, scope, approved base, autonomy and execution steps | Automatic approval or inferred delivery |
| Source journal | Significant findings, standing answers, accepted clause edits and provenance | Ordinary command transcripts or self-recorded validation success |
| Current decision view | Effective topic context and clause choices derived from accepted history | Independent handwritten authority |
| Member receipt | Validation of one exact member commit | Batch integration, delivery, or human acceptance |
| Final receipt | Complete validation of one exact frozen batch tip | Permission to deliver |
| Delivery result | Members, execution owners, batch identity, target identity, remote confirmation, cleanup | Human acceptance |
| Architecture | How the currently delivered system works | Pending behavior or historical rationale |

## Requirement coverage

Each owned requirement has observable acceptance and at least one execution
step. Explicit transfers name an active follow-up requirement; a prose promise
of later work does not carry unfinished scope. A changed contract needs actual
confirmation bound to its digest before implementation.

This proves coverage for recorded requirements, not perfect interpretation of
the original request. Historical Review, Specification and Plan packages remain
read-only authorities until explicitly migrated. A complete record or green
check does not imply delivery or human acceptance.

## Repository comprehension

An Agent begins at the architecture entry, follows responsibility documents,
loads mandatory and path/intent-selected policy, and searches production and
test implementations before proposing a change. It emits the selected policy
groups and reasons so routing is inspectable.

That manifest proves routing occurred; it is not proof of comprehension. Use the current decision working set and relevant implementation evidence.
Retrieve original rationale only when needed; do not maintain another report
repeating those authorities.

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
