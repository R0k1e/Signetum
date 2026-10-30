# Foundation has one evidence-backed public product surface

Status: Accepted
Review date: 2026-08-30
Supersedes: None
Superseded by: None

## Context

The Template already contains requirement traceability, isolated workspaces,
staged validation, frozen batches, and explicit delivery. A short package
description and command list do not let an evaluator understand those outcomes,
their limits, or the evidence a delivery produces. Undocumented mechanisms are
not a usable product, and promotional claims that are not tied to repository
contracts are not trustworthy.

## Decision

The root README is the concise product entry. It links to one Quickstart, a
small concepts map, workflow guides, customization guidance, and public
governance files. One checked-in example demonstrates the complete
Review-to-acceptance model without creating a second implementation authority.

Product claims use bounded language. Foundation can enforce coverage for
recorded clauses, evidence that discovery and routing occurred, exact validation
identity, and delivery provenance. It cannot guarantee correct interpretation
of requirements, defect-free software, or automatic adoption of later Template
changes.

Repository validation checks the required public assets and local Markdown
references through one check-only implementation. The check is part of the
existing validation graph and does not add a lifecycle operation.

## Consequences

- An adopter can evaluate the product without reading internal implementation.
- Documentation describes only behavior backed by current authorities.
- Broken public navigation fails validation instead of becoming stale silently.
- The Template remains independently owned after GitHub creates a repository.
