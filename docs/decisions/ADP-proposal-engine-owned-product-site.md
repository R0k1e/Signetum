# The engine owns a separately deployed RepoSeal product site

Status: Proposed
Review date: 2026-08-31
Supersedes: ADP-reposeal-is-the-public-product-identity.md
Superseded by: None

## Context

RepoSeal's default `main` branch is both the GitHub Template source and the
repository page GitHub surfaces by default. A product homepage wants the
canonical logo, comparisons, discovery metadata, and release evidence. A
clone-ready Template must not make every created repository inherit RepoSeal
branding and marketing files. One README cannot satisfy both ownership
boundaries cleanly.

## Decision

RepoSeal remains the sole public product identity and keeps the tagline “Seal
every change with evidence.” The `engine` branch owns a small static product
site, its tests, build authority, deployment workflow, and canonical brand
assets. GitHub Pages deploys only a validated disposable site artifact.

The rendered `main` branch remains the clone-ready Template and contains no
site source, Pages workflow, Logo asset, or marketing runtime. The GitHub
repository Homepage points to the deployed product page; GitHub remains the
source, release, and Template authority.

The site is bilingual, accessible, crawlable, and factual. It uses no
analytics, cookies, forms, third-party JavaScript, application framework, or
separate operational backend.

## Consequences

- RepoSeal gains one canonical human and machine-readable product entry.
- Repositories created from the Template remain immediately ownable and
  brand-free.
- Site changes follow the same Review, Specification, Plan, validation, batch,
  and delivery lifecycle as engine changes.
- The deployment artifact is disposable and never becomes a source authority.
