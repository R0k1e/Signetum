# Skill-first development

Status: Accepted
Review date: 2026-10-30
Supersedes: ADP-engine-release-and-current-authorities.md, ADP-reposeal-engine-and-template-are-separate-branches.md
Partially supersedes: ADP-engine-release-and-current-authorities.md, ADP-reposeal-engine-and-template-are-separate-branches.md
Superseded by: None

## Basis and boundaries

The owner chose one Signetum Skill entry for new and existing repositories.
The previous source/generated-branch split required two public identities and
release explanations. Main now owns product source; scaffolds remain internal.
The source verifier and local execution contracts stay shared and explicit.

Decision reasoning belongs once in its owning change; a standalone decision is
reserved for an independently maintained cross-change authority such as this
product migration. Ordinary implementation creates neither another ADR nor a
command transcript. Preserve accepted history and amend only affected clauses.

Pure matrices must not pay repository setup costs. Retain real source, runtime
and artifact traversals where their distinct boundary is actually at risk.
Revisit if observed consumer needs justify a separately published template or
a new execution boundary. Exact approved clauses and acceptance live in the
change record; this page retains the cross-change rationale.
