# Customizing the Template

A repository created from DevLoom is an independent repository. Customize
its copied authorities directly; do not add an upstream Template dependency.

## Replace product facts first

Update the root README, architecture map, repository manifest, focused policy,
fixtures, examples, package metadata, and release targets with product facts.
Delete teaching artifacts that are not true for the new product; do not leave
placeholder aliases or fallback identities.

## Preserve the lifecycle boundaries

If the repository keeps the DevLoom lifecycle, keep its public operations
explicit and non-interactive. Repository commands may project existing
authorities but must not duplicate selector, receipt, merge, or delivery logic.
Technology profiles should be selected from repository evidence.

## Changing the process later

1. Record the need as Review clauses.
2. Approve observable process behavior in a Specification.
3. Accept a standalone decision explaining the new authority and removed path.
4. Implement it in a Plan-owned worktree with behavior tests.
5. Deliver it through the repository's own batch lifecycle.

Another repository may manually implement the same idea as its own local
change. It does not pull an update from this Template.
