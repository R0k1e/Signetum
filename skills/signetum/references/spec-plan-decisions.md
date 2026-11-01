# Change approval

Open the repository-declared member workspace first. Run `change open <id>`
through the local utility. It creates one draft record at the returned path, using the
registered base. Fill its original intent, stable requirement IDs, observable
outcomes, acceptance, exclusions, transfers and execution autonomy. Execution
steps cover every owned requirement; routine steps can evolve without changing
behavior approval.

Run `view <record-path>` to generate a concise proposal. Show outcomes,
acceptance, scope and autonomy together. Lead with what the person needs to
decide, the recommended choice and material alternatives, their basis and impact.
Keep routine implementation details in the agreed autonomy; do not ask people to
review protocol syntax or repeated command output. This command never grants approval.
After the owner confirms, record that actual confirmation in `change.approval`
with actor, date, source and the generated contract digest. Do not invent a
confirmation or reuse its digest after changing behavior, base or autonomy.
Commit approval before implementation; implementation committed alongside a
new approval does not qualify as subsequent implementation.

Important architecture, process or security choices require an independently
identified, accepted decision transaction in the owning contract before implementation.
Keep its problem, material evidence, chosen rule and applicable boundaries once;
include alternatives and reopening conditions only when they change the choice.
Use `change reconcile` to append accepted decisions and derive current clauses. Amend
only affected clause IDs and preserve the other rules and original basis.

A standalone ADR is conditional: use it when the decision needs an independently
maintained cross-change authority. Put the reasoning there and reference it from
the change instead of expanding it twice. Ordinary implementation choices create
neither an ADR nor a journal event. Do not save transcripts or command attempts.

Use the actual confirmation and exact contract digest; preview and tool success
never confer acceptance. Preserve accepted historical records until an explicit
reviewed migration replaces their authority. Current architecture states implemented
rules; decision history preserves their formation. No word quota or second summary
is required.

Honor authorization already given in the conversation, including implementation,
integration or delivery. Show the generated final review before using existing
delivery authorization; request it only when missing. A scope change still needs
its own approval. Do not create another review document or standing summary.
