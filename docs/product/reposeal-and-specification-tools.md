# RepoSeal and specification tools

Specification tools help people and Agents describe intended behavior. RepoSeal
does not compete with that authoring experience. It governs what happens around
and after a Specification inside the repository.

| Question | Specification tool | RepoSeal |
| --- | --- | --- |
| What should the product do? | Helps author or manage a specification. | Requires approved observable behavior to own recorded Review clauses. |
| Did every requested clause get an owner? | Tool-dependent. | Checks Review-to-Specification ownership and Plan coverage. |
| Did the Agent understand the existing repository? | Usually outside scope. | Routes discovery through architecture and policy, then requires evidence in the Plan. |
| Can Agents implement in parallel safely? | Usually outside scope. | Uses Plan-owned branches and isolated worktrees. |
| How often does the full suite run? | Usually outside scope. | Uses targeted member feedback and one complete gate on the frozen batch. |
| What exactly was delivered? | Usually outside scope. | Records members, Plans, validated identity, delivery identity, and remote confirmation. |
| Is delivery the same as acceptance? | Tool-dependent. | Keeps delivery and human acceptance as separate states. |

Use RepoSeal by itself when repository-native YAML and Markdown are sufficient
for authoring. Use it alongside a specification tool when that tool improves
collaboration or drafting. In either case, the checked-in RepoSeal change package
is the delivery authority; chat history and external UI state are not.
