# Architecture and process decisions

Decision files explain why durable architecture, process, or security choices
were accepted. They do not describe current implementation facts; the
architecture map and responsibility pages own those facts.

New proposals begin as unnumbered `ADP-<slug>.md` files declaring
`Status: Proposed`, and must be accepted before implementation. The declared
status, not the file name, says whether a decision is still a proposal: an
accepted decision may stay unnumbered, and delivery numbers a proposal and
records its acceptance in the same step. Supersession is explicit: a new decision names the old
decision it replaces, while history remains intact.

Use repository search and the documentation validator to discover and verify
decision references rather than maintaining a second handwritten decision index.
