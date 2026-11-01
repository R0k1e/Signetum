# Working with Signetum

Install the Skill and start through [First use](../QUICKSTART.md). You describe
outcomes and acceptance; the Agent uses your existing project tools. Daily work
requires no upstream checkout or knowledge of the execution implementation.

## What to review

Before implementation, review desired behavior, included/excluded scope,
acceptance and autonomous execution. Ask for the important alternatives and
consequences when a choice matters. One approved change preserves that agreement.
The Agent keeps consequential reasoning in its journal and derives current
answers from it; routine logs do not become another document.

Before delivery, review the generated result: exact source, checks, changed tests,
resolved findings and remaining work. Passing checks does not grant delivery
permission or prove every requirement was understood. Existing authorization
remains usable within its scope; human acceptance is a separate state.

## Parallel development

Agree on member outcomes, shared interfaces, dependencies and an integration
owner. Each Agent develops in an isolated worktree. Named ready members are
integrated and the complete frozen result is validated before delivery. Your
Agent host launches the Agents; Signetum does not provide a global scheduler.

## Setup and updates

Ask the Agent to inspect an existing repository or initialize a new one, preserving
its tools. Adoption proposes one project configuration for review. Agent entry
files, application metadata and dependencies stay project-owned.

Ask the Agent to update Signetum to a named version or commit. It verifies the new
complete Skill and proposes project changes only when needed. Bare `update` displays
the procedure; checking and installation require explicit options. Ordinary work downloads
nothing. [Agent update instructions](../skills/signetum/references/adoption.md)
explain the exact boundary.

## Optional configuration

[Runner bindings](guides/existing-runners.md) retain existing application checks.
[Repository bindings](guides/repository-bindings.md) describe configuration and
versioned capabilities. [Structured selection](guides/structured-selection.md)
and [validation optimization](../skills/signetum/references/validation-optimization.md)
are conditional optimizations; full member validation is the default and final
validation remains complete.
