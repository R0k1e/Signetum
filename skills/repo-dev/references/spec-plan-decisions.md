# Change approval

Open the repository-declared member workspace first. Run `change-open <id>`
through the local utility. It creates one draft record at the returned path, using the
registered base. Fill its original intent, stable requirement IDs, observable
outcomes, acceptance, exclusions, transfers and execution autonomy. Execution
steps cover every owned requirement; routine steps can evolve without changing
behavior approval.

Run `view <record-path>` to generate a concise proposal. Show outcomes,
acceptance, scope and autonomy together. This command never grants approval.
After the owner confirms, record that actual confirmation in `change.approval`
with actor, date, source and the generated contract digest. Do not invent a
confirmation or reuse its digest after changing behavior, base or autonomy.
Commit approval before implementation; implementation committed alongside a
new approval does not qualify as subsequent implementation.

For a durable architecture, process or security choice, create an independently
identified decision transaction in the contract. Include context, affected
clause IDs, expected prior versions, scope and rationale. Its exact proposal
requires acceptance before implementation. Use `reconcile` to place that
accepted transaction in history and derive the current working set. Amend,
withdraw, split or merge only the affected clauses; preserve unaffected rules.
A preview, draft mapping or tool success cannot accept a decision.

Existing accepted behavior and accepted history remain authoritative. Use a new
change for a later outcome. Preserve historical Markdown decisions until an
explicit, reviewed migration replaces their authority.

Keep the minimum record needed to reconstruct a consequential choice: the problem,
material alternatives, evidence for the selected option, and when to reconsider it.
Only include alternatives that affected the decision. Ordinary implementation
choices need no standalone decision. Reference the original basis rather than
copying it into architecture, plans and reports. Current clauses state the rule;
history preserves its formation. Do not save chat transcripts or every attempt,
and do not replace rationale with a conclusion alone. No fixed word budget or
mandatory template for every small choice is needed.
