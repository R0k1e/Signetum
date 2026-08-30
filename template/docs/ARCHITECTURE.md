# Architecture

This file is the first discovery authority for every Agent. Replace the
bracketed facts when the repository is created; keep the responsibility links
stable as the product evolves.

## Product boundary

- Product: `[name and user-visible purpose]`
- Public entry points: `[CLI, API, UI, jobs, or libraries]`
- Production implementation roots: `[paths]`
- Test roots: `[paths]`
- Environment authority: `[mise, uv, npm, cargo, or another repository-owned tool]`

## Responsibilities

- [Development lifecycle](development-lifecycle.md)
- [Agent-team delivery](agent-team-delivery.md)
- [Customization](customizing.md)

Search all production and test implementations before changing an authority.
Extend one owner and remove superseded implementations and compatibility paths.
