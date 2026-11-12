# Change approval

Open the repository-declared member workspace first. Run `change open <id>`
through the local utility. It creates one draft record at the returned path, using the
registered base. Fill its original intent, stable requirement IDs, observable
outcomes, acceptance, exclusions, transfers and execution autonomy. Execution
steps cover every owned requirement; routine steps can evolve without changing
behavior approval.

Run `change view <record-path>` to generate a concise proposal. Show outcomes,
acceptance, scope and autonomy together. Lead with what the person needs to
decide, the recommended choice and material alternatives, their basis and impact.
Keep routine implementation details in the agreed autonomy; do not ask people to
review protocol syntax or repeated command output. This command never grants approval.
After the owner confirms, record `change.approval` with `actor`, `recorded_at`
and one neutral `statement`. Never quote the owner verbatim. Commit authorization
alone before the first implementation commit; bundled authorization does not
qualify. Authorization is recorded once. Later scope changes update change.toml
and are recorded only, without contract-digest binding or re-approval. Final
review derives and lists those revisions from source history per change, starting
at the first change.toml that parses as an approved record. Earlier unparseable
drafts stay in the review with their commit and parse cause and never count as
approval. An unparseable record after authorization fails review even when a later
commit is valid. Record `recorded_at`; `date` is not accepted as that field.

Trace to the root cause before asking. Ask related questions together, once.
The coordinating Agent decides package splits, ordering and batching and reports
them. Never write the owner's rejections into any record.

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

Use the actual authorization; preview and tool success
never confer acceptance. Preserve accepted historical records until an explicit
reviewed migration replaces their authority. Current architecture states implemented
rules; decision history preserves their formation. No word quota or second summary
is required.

Honor authorization already given in the conversation, including implementation,
integration or delivery. Show the generated final review before using existing
delivery authorization; request it only when missing. Record later scope changes without re-approval. Do not create another review document or standing summary.

## Closing an owned change

Use this section only for an implemented change; read-only assistance has no
change record or delivery lifecycle to close.

Read the owning record and the current decision working set. Check each stable
requirement against its acceptance evidence and execution steps. A selected
subset of work or an agent report cannot close remaining obligations. Generated
views and receipts explain status; they are not another maintained authority.

A deferral states who decided and what remains owed, and may name an approved
follow-up change. It stays visible in the source log and in the final review's
unfinished work. An omitted requirement, prose
non-goal or arbitrary file cannot carry unfinished work. Record scope reductions and changed outcomes in change.toml; final review lists
the revisions without requiring new authorization.

Use `status` to inspect findings. Resolve or justify rejection through the
journal tools; retract an incorrect answer by its exact resolution ID, then
supply a corrected answer. Retire obsolete evidence only through an exact
approved retirement proposal. Preserve the original answer and its basis.
`change history` retrieves those details on demand.

Before claiming completion, verify every approved outcome and named deliverable
against actual evidence. Keep the whole change open for unfulfilled obligations.
Check affected architecture, command examples, prerequisites and Skill references
against the implemented behavior. Update stale current guidance; leave unaffected
pages alone. A passing link check does not establish factual accuracy. Resolve significant findings in the existing journal. Unchanged authorities
need no routine event, checklist or report.
Ready, integration, delivery and explicit human acceptance remain distinct.
