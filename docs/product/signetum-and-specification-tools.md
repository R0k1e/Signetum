# Signetum and specification tools

Specification tools help people and Agents describe intended behavior. Signetum
does not compete with that authoring experience. It governs what happens around
and after an approved specification inside the repository.

| Question | Specification tool | Signetum |
| --- | --- | --- |
| What should the product do? | Helps author or manage a specification. | Requires approved observable behavior for recorded requirements. |
| Did every requested clause get an owner? | Tool-dependent. | Checks stable requirement identities and exhaustive execution ownership in the change record. |
| Did the Agent understand the existing repository? | Usually outside scope. | Routes discovery through architecture and policy, then keeps the relevant basis in the owning change. |
| Can Agents implement in parallel safely? | Usually outside scope. | Uses change-owned branches and isolated worktrees. |
| How often does the full suite run? | Usually outside scope. | Offers focused diagnostics; ready runs the declared member gate and final checks the complete batch. |
| What exactly was delivered? | Usually outside scope. | Records members, execution owners, validated identity, delivery identity, and remote confirmation. |
| Is delivery the same as acceptance? | Tool-dependent. | Keeps delivery and human acceptance as separate states. |

Use Signetum by itself when a repository-native structured change record is sufficient
for authoring. Use it alongside a specification tool when that tool improves
collaboration or drafting. In either case, the checked-in Signetum change package
is the delivery authority; chat history and external UI state are not. Historical
Review, Specification and Plan packages remain readable during explicit migration.
