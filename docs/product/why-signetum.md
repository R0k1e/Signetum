# Why Signetum exists

Signetum is a reliable agentic development and delivery protocol: one standard
Skill, repository-owned instructions and local commands that connect an approved
change to its implementation, evidence and explicit delivery.

An Agent can produce working code while losing a requirement, repeating an old
decision or reporting success for a commit that was never checked. Signetum makes
these obligations inspectable after the conversation has ended.

## Built from development, used in development

The repository and Skill exist to make development and review easier. Maintaining
the protocol is part of that cost. Signetum develops itself through the shipped
protocol and implementation owners, so self-use problems become product repair
inputs rather than private exceptions.

Perdura is an originating application and a continuing source of real problems
and validated lessons. Reusable experience belongs in Signetum; application
selection rules, paths and product policy remain with the consuming repository.
This experience transfer does not mean Perdura adoption is already complete.

The intended audience includes large teams of coding Agents. Explain the product
through concrete failures, the repairs made and evidence of their outcomes.
Mechanism demonstrations do not establish a measured deployment scale or a
general reduction in review time or defects. Installation, distribution and first
use must remain simple and must be exercised through the actual entrypoints.

## One change, one record

New work starts with one structured change record. It keeps the intent, stable
requirements, acceptance, autonomy and execution steps together. Tools generate
the approval view; the owner confirms the exact contract before implementation.
An omitted requirement or unapproved contract cannot qualify for readiness.
Historical Review, Specification and Plan packages remain readable during
migration; new work does not require three parallel handwritten documents.

## History for explanation, a working set for action

Significant findings and accepted decision edits enter an append-only source
journal through local tools. Stable decision clauses can be amended individually;
unaffected clauses retain their authority. A topic-organized current working set
is derived from accepted history, with original rationale available on demand.
It is not another summary for Agents to maintain by hand. Until historical
adoption is complete, relevant legacy decisions must still be consulted.

## Evidence has an identity

Readiness binds the exact member commit and declared validation inputs. A later
commit needs fresh evidence. Diagnostic retry success does not erase the first
failure. An explicit batch combines named ready members and validates its frozen
source before delivery. Publication confirms the remote identity before moving
the local delivery target, and interrupted publication has an explicit retry path.

These are observable contracts, not a guarantee that every requirement was
understood or that passing software contains no defects. The protocol does not
replace the repository's behavioral tests or the owner's review.

## Start with your existing repository

Keep the application's runner and environment authority. The protocol core does
not prescribe an application language; optional Python, Node and Rust bindings
reuse existing commands. Installing the Skill alone neither adopts the protocol
nor authorizes delivery. See the [existing-runner adoption guide](../guides/existing-runners.md).

Try the [minimal example and failure demonstrations](failure-demonstrations.md),
then read the [practice article](protocol-in-practice.md). The
[Quickstart](../../QUICKSTART.md) covers a new Template repository.

The distribution is local and repository-owned. There is no cross-machine
ledger, account service or automatic workflow upgrade. Reduced review time,
fewer defects and faster delivery are intended benefits, not measured results
claimed by this release.
