# Specification, Plan, and decision gates

Read this reference when behavior or durable engineering policy may change, or
when drafting, reviewing, reopening, or superseding a Specification or Plan.

## Specification gate

New observable behavior requires a human-confirmed Specification before tests
or implementation. Read the owning Review clauses first. Capture inputs,
outputs, positive and negative contracts, invariants, boundaries, and explicit
ownership or transfer relationships using the repository-declared schema.

Changing accepted behavior requires a new or superseding approved contract;
do not edit accepted history in place. A bug that violates the accepted
contract does not require inventing a changed contract, but follow the
repository's defect/reopen rules and reproduce it at the public boundary.

## Decision gate

Durable architecture, process, or security decisions require a standalone
accepted decision before implementation. Record alternatives and why they
were rejected. Keep implementation convenience out of the decision authority.

## Plan gate

Create a Plan only from an approved Specification and approved required
decisions. Bind it to the repository-declared base and workspace authority.
The Plan must exhaust every owned Specification obligation and name observable
acceptance evidence. Include affected authorities, reuse and single-owner
analysis, positive and negative cases, dependencies, file boundaries, and
exact repository-declared validation commands where applicable.

Audit and refactor analysis requires human approval before implementation.
Dispatches select Plan obligations and cannot redefine their scope. Any scope
change returns to Review/Specification approval; any deferral first transfers
ownership to another approved Specification.
