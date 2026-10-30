# Engine-owned RepoSeal product site

Status: approved for implementation
Specification: `changes/public-product-site/specs/engine-owned-pages.toml`
Base: `engine@5cb7473644e986114930e08772cab2252de7e2df`

## Obligations

| ID | Clauses | Outcome |
| --- | --- | --- |
| SITE-P1 | SITE-001, SITE-002 | Build accessible English and Chinese static pages using the canonical mark, one visual system, and evidence-backed product copy. |
| SITE-P2 | SITE-002 | Add canonical, hreflang, Open Graph, social, `SoftwareApplication` JSON-LD, robots, and sitemap metadata. |
| SITE-P3 | SITE-003 | Keep source under engine `site/`, stage a disposable exact artifact, and prove `template/` and rendered `main` inventories remain brand-free. |
| SITE-P4 | SITE-004 | Add a pinned GitHub Pages workflow triggered only by delivered `engine` changes to site-owned paths or explicit dispatch. |
| SITE-P5 | SITE-001, SITE-003, SITE-004 | Validate HTML structure, local links, metadata, asset identity, artifact inventory, and mobile layout before deployment. |
| SITE-P6 | SITE-005 | After a successful Pages deployment, set the GitHub Homepage to the deployed canonical URL and verify it publicly. |

## Product and technical boundary

| Knowledge | Authority |
| --- | --- |
| Product claims | engine README, architecture, accepted decisions, and released behavior |
| Canonical mark | `assets/brand/reposeal-mark.png` and deterministic derivatives |
| Site source | `site/` on `engine` |
| Site build | one repository-owned standard-library build script |
| Deployment | one pinned `.github/workflows/pages.yml` workflow |
| Clone-ready product | `template/` rendered to `main`, unchanged by the site |

## Page information architecture

1. Hero: RepoSeal, “Seal every change with evidence”, GitHub and Template CTAs.
2. Six outcomes: requirement closure, repository understanding, lower validation I/O,
   parallel Agent teams, explainable delivery, behavior-focused quality.
3. Lifecycle: Review → Specification → Plan → worktree → batch → final → delivery → acceptance.
4. Comparison: complements Specification tools, is broader than CI, and is not an Agent runtime.
5. Evidence: v0.2 capabilities, exact release link, language-neutral Core and Python default.
6. Boundaries and ownership: copied repositories evolve independently.

English is canonical at `/RepoSeal/`; Simplified Chinese is at
`/RepoSeal/zh-CN/`. The design uses the navy/teal/off-white brand palette,
large readable type, restrained motion honoring `prefers-reduced-motion`, and
no client-side application framework.

## Build and deployment flow

```text
engine/site + canonical brand assets
  → repository build script
  → disposable exact Pages artifact
  → structural and link validation
  → pinned upload-pages-artifact
  → explicit deploy-pages environment
```

The artifact contains only HTML, CSS, public image derivatives, `robots.txt`,
and `sitemap.xml`. It never contains engine source, change packages, receipts,
or Template files.

## Acceptance

```text
uv run pytest <site contract tests>
just ready <approved-engine-base>
just final
```

After delivery, verify the Pages workflow, public English and Chinese URLs,
metadata, responsive screenshots, and the GitHub Homepage field.
