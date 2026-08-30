# Agent Team batch delivery

An Agent Team scales implementation by isolating members and sharing only the
explicit batch boundary.

```text
approved base
  +-- member A worktree -> commit A -> ready receipt A --+
  +-- member B worktree -> commit B -> ready receipt B --+-> named batch
  +-- member C worktree -> commit C -> ready receipt C --+      |
                                                               final once
                                                                   |
                                                          explicit delivery
```

## Member rules

- Each development task uses a Plan-owned worktree created from the exact approved base.
- A member contains one coherent, independently reviewable outcome.
- Targeted or changed validation supplies fast feedback during implementation.
- `ready` binds evidence to the member's exact commit, not its branch name.
- Members never merge themselves into the delivery branch or enumerate peers.

## Batch rules

- `batch-open` and `batch-admit` require explicit `--member` paths.
- Admission merges member branches without rewriting them.
- A member can rejoin after a later ready fix; its history is not permanently consumed.
- Conflicts finish through `batch-continue` after repair and changed validation.
- Complete validation runs once on the frozen batch tip.

## Delivery evidence

The delivery result is machine-readable and reports:

- approved base;
- each member branch, original commit, integrated commit, patch identity, and summary;
- delivered Plan paths;
- exact validated batch tip and final receipt;
- resulting delivery and remote commit;
- worktrees and branches removed only after remote confirmation.

This lets a reviewer answer “what shipped?” without reconstructing it from chat
or relying on an Agent summary.

## Human boundaries

Agents may perform ordinary implementation and validation inside the approved
scope. Human confirmation remains necessary for Specification meaning, durable
architecture/process/security decisions, scope exclusion or deferral, explicit
delivery, and acceptance of delivered clauses.
