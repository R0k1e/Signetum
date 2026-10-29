# Signetum

<p align="center">
  <img src="assets/brand/signetum-mark-256.png" width="180" alt="Signetum logo: a seal holding a verified repository with a Git branch on its flipper">
</p>

[![CI](https://github.com/R0k1e/Signetum/actions/workflows/ci.yml/badge.svg)](https://github.com/R0k1e/Signetum/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

**Seal every change with evidence.**

Signetum is a reliable agentic development and delivery protocol, distributed as
one standard Skill plus repository-owned local commands. It connects approved
requirements, current decisions, implementation evidence and explicit delivery.
A clone-ready GitHub Template is available for new repositories.

Use it when coding Agents need to preserve decisions across sessions, the owner
needs a compact review of a change, or several members need an explicit shared
delivery boundary.

It gives a repository one inspectable development lifecycle instead of relying
on chat history, an Agent's memory, or an unstructured collection of scripts.
The default branch is a rendered, clone-ready Template. A repository created
from it owns its copy and evolves independently; there is no upstream
synchronization contract. Signetum engine development stays on the `engine`
branch; the rendered Template carries only its reviewed, standard-library
lifecycle runtime and does not install the Signetum package.

## What it provides

| Outcome | Repository contract |
| --- | --- |
| Recorded requirements do not disappear silently | One approved change record binds stable requirements, acceptance and exhaustive execution steps. |
| Agents inspect before changing | Architecture and repository policy route discovery to named authorities and require an inspectable routing manifest. |
| Validation is explicit | Members run all declared member checks by default; an optional repository provider enables selection. Final validates the complete frozen batch. |
| Agent Teams work safely in parallel | Each member uses an isolated plan-owned worktree and cannot mutate the delivery worktree. |
| Every delivery is explainable | The delivery result names the requirements, Plans, member commits, validated batch tip, and delivery commit. |
| Tests protect product behavior | Unit tests cover pure contracts; integration tests traverse real public boundaries; implementation-detail assertions are rejected by policy. |
| Humans retain consequential decisions | Specification, architecture/process/security decisions, scope deferral, acceptance, and delivery remain explicit. |
| Failed workflows remain recoverable | The lifecycle avoids history rewriting and preserves evidence until remote delivery is confirmed. |

Signetum can mechanically prove coverage for requirements that were recorded,
the exact tree that was validated, and what entered a delivery. It cannot prove
that natural language was interpreted perfectly or that software is defect-free.

The Core is language-neutral. A repository can compose multiple language
profiles without changing the lifecycle; the public Template enables a
batteries-included Python default with uv, Ruff, ty, behavioral tests, and
security checks. Optional [existing-runner bindings](docs/guides/existing-runners.md)
retain Python, Node and Rust repository commands without changing their test
frameworks or application metadata.

Daily use is: describe a change, review its proposal, let the agent implement and
check it, then inspect readiness. `protocol status` explains the current state
and next step. `changed --explain` previews checks without running them; use it
only when the plan needs inspection. Test, ready and final retain their separate
roles. Recovery and optional optimization commands are conditional references,
not extra steps every change must perform.

## The lifecycle

```text
registered member -> approved change record -> implementation
       -> member ready -> named batch -> final validation
       -> explicit delivery -> human acceptance or reopening
```

The normal path is workspace creation, member readiness, named batch assembly,
frozen final validation, and explicit delivery. Supported synchronization,
preparation and cleanup have the same machine-readable result contract.
See [Validation and delivery](docs/architecture/validation-and-delivery.md#workspace-operations)
for the operation catalog and recovery rules.

## Skill distribution

Install the standard [`repo-dev` skill folder](https://github.com/R0k1e/Signetum/tree/engine/skills/repo-dev)
with your coding agent's skill installer. It contains `SKILL.md`, conditional
references and a local launcher; the built wheel includes the same folder.
The launcher uses the adopted local runtime, or an existing `just protocol` binding.
Installation does not adopt a workflow, download a runtime or change a project.
Existing repositories bind their local runtime and runners through an explicit
reviewed adoption change. The skill points back here for maintained extensions.

The Signetum engine and the rendered Template use independent semantic
versions. The package version identifies an engine release; `template_version`
identifies the clone-ready repository revision and does not mirror the package
number.

## Start here

Install the [`repo-dev` Skill](https://github.com/R0k1e/Signetum/tree/engine/skills/repo-dev)
with your coding agent's skill installer, then follow the [first-use guide](QUICKSTART.md).
Ask the agent:

> Use repo-dev to inspect this repository and prepare a Signetum adoption preview.
> Keep our existing tools and show me the changes before applying them.

After adoption, describe development tasks normally. The agent prepares the
change record and evidence; you review the intended behavior, consequential
choices and delivery result. You do not need to edit journal formats or assemble
protocol requests.

For a new repository, GitHub's **Use this template** action supplies the local
runtime. Existing repositories use the same [reviewed adoption path](docs/guides/existing-runners.md).
The [failure demonstrations](docs/product/failure-demonstrations.md) show what
happens when requirements, checks or source identities do not match.

See the [documentation map](docs/README.md) for operation, customization and
maintainer references. [Working with a change](docs/product/protocol-in-practice.md)
explains what the owner reviews and what the agent records.

## Validate the Template

```bash
uv sync --locked
uv run signetum check product-surface --repository .
uv run signetum check traceability --repository .
uv build
uv run signetum protocol test --shard engine:pytest
uv run signetum protocol test --shard engine:world-tests
```

The `signetum` CLI emits one JSON result and exits nonzero for invalid
contracts. Signetum is both the product and machine protocol identity. See
[Architecture](docs/ARCHITECTURE.md) for current responsibility boundaries.

## Project boundaries

- The protocol is local and repository-owned; it provides no cross-machine
  ledger, account service or automatic workflow adoption.
- It does not update repositories previously created from it.
- It does not replace product-specific architecture, tests, or human review.
- Validation is check-only. Publication and delivery require explicit authority.

See [Contributing](CONTRIBUTING.md), [Security](SECURITY.md),
[Changelog](CHANGELOG.md), and the [Apache-2.0 license](LICENSE).
Maintainers should follow the [release guide](docs/maintainers/releasing.md)
before creating a version tag or publishing artifacts.
