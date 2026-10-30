# Parallel development and batch delivery

Each coherent change has an approved record and isolated member workspace.
Members develop independently; one operator integrates only explicitly named
members into a batch. `ready` binds checks to a member's exact commit.

```text
member A -> ready A --+
member B -> ready B --+-> named batch -> full final -> explicit delivery
member C -> ready C --+
```

Use targeted test diagnostics during implementation. `changed` only explains
selection. Members neither enumerate peers nor merge into the delivery branch.
Admission holds the batch exclusively, merges qualified members and prepares and
statically checks the combined tree. Conflicts remain open for `batch-continue`;
continuation runs preparation and batch checks, not another member test pass.

If final fails, repair the owning member, commit and run ready, then admit its
new tip into the same batch. History is retained. Run final on the new frozen
batch; an earlier receipt cannot qualify it.

The generated review binds approvals, retained discoveries, exact source and
admitted evidence. Present it before requesting explicit delivery. Delivery
confirms the remote before updating the target and performs only eligible cleanup.
It proves neither package publication nor human acceptance.

[Delivery and recovery](../../skills/signetum/references/delivery-recovery.md)
owns the operation procedure; [validation responsibilities](../architecture/validation-and-delivery.md)
own evidence, locking and failure semantics. Do not maintain a parallel command
list or handwritten delivery report.
