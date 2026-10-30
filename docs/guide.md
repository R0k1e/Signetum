# Working with Signetum

Signetum connects an approved change, significant decisions, checked source and
explicit delivery. Install the standard Skill and follow [First use](../QUICKSTART.md).
New and existing projects use the same reviewed adoption path and retain their
application language and runner. Git, a host Python interpreter and the declared
Mise/Worktrunk workspace tools are protocol prerequisites.

## One change and its basis

Ask the agent for the desired behavior. It reads architecture, selected policies
and the current decision working set, then prepares `changes/<id>/change.toml`.
Review outcomes, acceptance, excluded scope and execution autonomy. Approval binds
that exact contract; it is not inferred from a preview, filename or green test.

The agent keeps consequential discoveries and accepted clause changes in the
change's append journal. The current decision set is derived from that history;
a small amendment changes named clauses, retaining their context and rationale.
Routine command output stays in receipts and logs. No second handwritten summary
or execution diary is required. Relevant historical decisions remain readable;
a new empty journal does not erase them.

## Daily feedback and test changes

`status` explains the current workspace and recorded evidence without checks.
`changed --explain` shows the check plan. Use the configured `test` diagnostic for
explicit feedback; `ready` validates a clean, committed member. Full member
validation is the default. Optional structured selection can narrow tests while
unknown inputs fall back and modified test files retain whole-file coverage.

The agent must tell you which tests it modifies, why and what evidence remains or
replaces them. Removed coverage, relaxed assertions, skips and threshold changes
are disclosed separately. A passing test cannot silently redefine the approved
outcome. Final review summarizes actual changes and checks, not a copied log.

## Parallel work and delivery

Each member owns an isolated worktree and immutable base. Named ready members
enter a batch through `batch-open` or `batch-admit`; conflicts use
`batch-continue`. Admission prepares and checks integration without secretly
repeating member suites. `final` validates the complete frozen batch and generates
its review. Delivery is a separate, explicitly authorized `batch-deliver` naming
source, target, expected base and exact batch tip.

Evidence belongs to the checked commit and inputs. An edited or reworded tip needs
fresh readiness; a diagnostic retry never clears a first failure. World checks,
such as an advisory audit, are fresh final obligations rather than reusable
member evidence. Approved waivers are explicit and expire; they are not passes.

Review approved outcomes, delivered behavior, test changes, evidence and unfinished
work before delivery. The publisher confirms the remote identity before moving
the local target. On interruption, inspect exact identities and retry through the
same operation; never force-push or substitute an ad-hoc merge. Cleanup preserves
unrelated state and the executing runtime, which can be removed from a safe
checkout after the operation finishes.

## What a profile does

A profile is a versioned capability declaration: what it owns and which declared
capabilities it depends on. Composition checks supported identities, dependency
cycles and conflicting ownership. The resolved identities are bound into evidence.
Selecting a profile does not execute omitted commands or detect an application
language. The repository's explicit tools, shards and gates remain the executable
truth. Existing-runner configuration can be retained directly; optional Python,
Node and Rust adapters emit reviewed bindings rather than replacing application
metadata. See [runner bindings](guides/existing-runners.md).

## Limits and extensions

Signetum checks recorded requirement accounting and exact validation identity; it
does not prove that natural language was understood or software has no defects.
Delivery does not imply human acceptance. Installing or updating the Skill does
not automatically adopt or upgrade a repository. Updates are explicit previews.

A specification authoring tool can help draft requirements; the repository's
approved change remains the delivery authority. Optional selection, weighted
scheduling and CI partitioning use repository-owned inputs and preserve complete
final validation. See [selection](guides/structured-selection.md) and
[validation optimization](../skills/signetum/references/validation-optimization.md).

## Finding the right documentation

[Architecture](ARCHITECTURE.md) describes implementation owners and invariants.
This guide explains daily use; `guides/` holds optional configuration details.
`maintainers/` is for developing and releasing Signetum itself, including the
planned Perdura integration, rather than required reading for consumers.
The `maintenance` command group is separate: it prepares or synchronizes local
workspaces and safely cleans up completed work. It is not another daily lifecycle.

After publishing a review branch, its publisher owns remote ref cleanup. Delete
only its exact inspected tip once it is reachable from the delivery branch;
refuse changed tips and preserve unmerged work. Local workspace cleanup does not
implicitly remove remote refs. Use a readable review name when sharing a candidate;
internal batch identifiers are implementation provenance, not user-facing names.
