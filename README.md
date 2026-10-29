# Signetum

The Signetum engine and the rendered Template use independent semantic
versions. The package version identifies an engine release; `template_version`
identifies the clone-ready repository revision and does not mirror the package
number.

<p align="center">
  <img src="assets/brand/signetum-mark-256.png" width="180" alt="Signetum logo: a seal holding a verified repository with a Git branch on its flipper">
</p>

[![CI](https://github.com/R0k1e/Signetum/actions/workflows/ci.yml/badge.svg)](https://github.com/R0k1e/Signetum/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

**Seal every change with evidence.**

Signetum is an Agent-native GitHub Template for teams that want coding Agents to
work quickly without losing requirements, duplicating repository authorities,
overwriting parallel work, or delivering a green commit nobody can explain.

Use it when multiple coding Agents contribute to one repository, requirements
must remain traceable after chat context disappears, or repeated full-suite
testing is making parallel delivery unnecessarily slow.

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
| Development feedback stays fast | Members run targeted or changed validation; complete validation runs once on the frozen batch. |
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
security checks.

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
The launcher calls the consuming repository's `just protocol` commands.
Installation does not adopt a workflow, download a runtime or change a project.
Existing repositories bind their local runtime and runners through an explicit
reviewed adoption change. The skill points back here for maintained extensions.

## Start here

1. Create a new repository with GitHub's **Use this template** action.
2. Follow [Quickstart](QUICKSTART.md) to complete one governed change.
3. Read [Development lifecycle](docs/concepts/development-lifecycle.md) for the
   boundary between the change contract, source history, evidence and acceptance.
4. Use [Agent Team delivery](docs/workflows/agent-team-delivery.md) for parallel
   members and batch delivery.
5. Read [Customizing the Template](docs/guides/customizing-the-template.md)
   before changing repository authorities.

See the [documentation map](docs/README.md), [why Signetum exists](docs/product/why-signetum.md),
and [frequently asked questions](docs/product/frequently-asked-questions.md)
for evaluation and comparison. If you already use a specification tool, read
[Signetum and specification tools](docs/product/signetum-and-specification-tools.md).
Copied v0.1 repositories can use the explicit
[v0.2 adoption guide](docs/guides/upgrading-v0.1-to-v0.2.md).

A complete, non-authoritative teaching artifact is available under
[`examples/complete-change`](examples/complete-change/README.md).

## Validate the Template

```bash
uv sync --locked
uv run signetum check product-surface --repository .
uv run signetum check traceability --repository .
uv run pytest
uv build
```

The `signetum` CLI emits one JSON result and exits nonzero for invalid
contracts. Signetum is both the product and machine protocol identity. See
[Architecture](docs/ARCHITECTURE.md) for current responsibility boundaries.

## Project boundaries

- This is a development lifecycle Template, not an Agent runtime or hosted
  service.
- It does not update repositories previously created from it.
- It does not replace product-specific architecture, tests, or human review.
- Validation is check-only. Publication and delivery require explicit authority.

See [Contributing](CONTRIBUTING.md), [Security](SECURITY.md),
[Changelog](CHANGELOG.md), and the [Apache-2.0 license](LICENSE).
Maintainers should follow the [release guide](docs/maintainers/releasing.md)
before creating a version tag or publishing artifacts.
