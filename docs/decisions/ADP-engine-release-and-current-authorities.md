# Engine publication and current authorities

Status: Accepted
Review date: 2026-10-30
Supersedes: None
Superseded by: ADP-skill-first-development.md

## Context

The owner requested a reachable Signetum repository, one publication path and
current architecture maintained during development. Public metadata still used
RepoSeal, release guidance named main although main is the rendered Template,
and an unused local preflight depended on machine-local receipts.

## Decision

Use Signetum as the canonical repository identity. Engine and bundled Skill
artifacts share the exact delivered engine source; main remains the independently
versioned rendered Template. One preflight verifies clean exact source, delivered
engine ancestry, component versions and a supplied release tag. CI calls that
same verifier before building. A tag or preflight never authorizes publication.

Reconcile affected current architecture, commands and prerequisites in the same
implementation change. Read the relevant authorities during planning and check
them at closure. Preserve rationale in history; update only affected current
guidance. Do not add another report or prose-matching gate.

Skill installation supplies instructions; existing-repository adoption needs one
reviewed engine and explicit approval. Afterwards local runtime owns execution.
Keep this distinction and prerequisites visible before an agent tries commands.

## Alternatives and reopening

Publishing from main would publish a template without engine sources. Requiring
local receipts in hosted CI would create a second execution or transfer channel.
Blindly matching documentation prose would constrain wording without establishing
truth. Revisit if engine and Template move to separate repositories, a published
bootstrap artifact removes the one-time engine step, or observed drift justifies
a narrow structural check. No code delivery or release is authorized here.
