# A Skill owns its development runtime

Status: Accepted
Review date: 2026-10-31
Supersedes: ADP-0003-mise-and-worktrunk-authorities.md
Partially supersedes: ADP-0003-mise-and-worktrunk-authorities.md
Superseded by: None

The owner approves one standard Skill containing the maintained engine source.
Its locked non-editable environment lives beside the installed Skill, not in an
application environment or committed consumer runtime. Mise and Worktrunk remain
development authorities. Setup is explicit; ordinary calls do not install,
update or grant trust. Engine content identity is observed with validation.

One reviewed project manifest owns execution bindings and delivery facts. Existing
Agent entrypoints, architecture and project checks remain project-owned. Adoption
does not add pointers, policy copies, governance documents or engine source.
Only exact reviewed unchanged previously managed files may be removed.

Named integration keeps structured source proof in real merge commits. There is
no empty provenance commit and no semantic dependence on a human-facing title.
Existing commit hooks remain enabled. First failures, immutable bases, complete
final checks, source-bound reviews and remote-first exact delivery remain intact.

Current decisions and significant reasoning remain source-owned. Default views
do not enumerate the historical corpus; agents read existing sources on demand.

## Supersession boundary

Replace only the copied self-contained runtime requirement of the named earlier
decision. Retain Mise/Worktrunk ownership. Current architecture and Skill guidance
state the adopted boundary; original rationale and delivered history remain.
