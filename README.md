# Signetum

<p align="center">
  <img src="assets/brand/signetum-mark.svg" width="80" alt="Signetum signet">
</p>

**Shared decisions. Parallel agent development. Reliable delivery.**

Signetum helps people make key decisions and multiple coding agents work in
isolated worktrees. Agree on the outcome, divide the work, integrate deliberately
and deliver the exact source you reviewed. One standard Skill guides the process
for new projects and existing repositories, using their own application tools.

## Install and start

Install [`skills/signetum`](https://github.com/R0k1e/Signetum/tree/main/skills/signetum)
with your agent's standard Skill installer. Select an exact reviewed release tag
or commit for reproducibility. Skill installation does not update previously
adopted repositories.

Then ask:

> Use $signetum to set up this new project, or inspect and adopt this existing
> repository. Preserve its tools and show the proposed changes first.

The agent obtains a fixed-version setup tool, inspects the project and prepares
minimal local bindings. You review the preview. After adoption, the Skill calls
the repository's local runtime; normal development needs neither an upstream
checkout nor repeated tool downloads. See [First use](QUICKSTART.md).

For a development task, describe the behavior normally. Discuss consequential
choices with the agent, then approve the outcome and acceptance. For parallel
work, agree on task boundaries, dependencies, shared interfaces and an integration
owner. You or your coding-agent host organize the agents; each member develops
in an isolated worktree. Qualified changes enter a named batch for complete
validation and explicit delivery.

## What it gives you

- Key decisions and their basis kept once, with a derived current decision set.
- Clear ownership, dependencies and isolated worktrees for parallel agent changes.
- Named integration, complete final checks and delivery of an exact reviewed source.
- Behavioral tests through existing tools; optional project selectors and bounded
  test scheduling can improve feedback without weakening final validation.

The runtime is language-neutral and uses a host Python interpreter. It can retain
Python, Node, Rust or other application runners. Signetum is a development and
delivery protocol, not an automatic global agent or machine-resource scheduler.
It provides no remote ledger or automatic consumer updates.

## Maintained source

`main` owns the Skill, setup/runtime implementation and documentation. The
`tests/fixtures/portable-python/` directory is internal runtime test material, not a
second installation route or independently published product. The package bundles
the same standard Skill folder; there is one source and release path.

[Documentation](docs/README.md) covers usage and configuration.
[Architecture](docs/ARCHITECTURE.md), [Contributing](CONTRIBUTING.md) and
[releasing](docs/maintainers/releasing.md) describe maintenance.
[Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [Apache-2.0](LICENSE)
