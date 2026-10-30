# Contributing

Use the [Signetum Skill](skills/signetum/SKILL.md) and the repository's `AGENTS.md`,
architecture entry and selected policies. Search existing production and test
owners before proposing a change. New work uses one `changes/<id>/change.toml`
and significant append history; generate its approval view and record actual
confirmation before implementation. Routine work creates no extra report or ADR.

Use an isolated member workspace and the declared uv environment. For focused
feedback, run `just test <affected-paths-or-pytest-options>`. Build with `uv build`
before installed-artifact tests. `changed` explains selection without checks;
`ready` validates a committed member. Extend or consolidate existing tests at the
cheapest boundary that exposes the risk.

The [validation responsibilities](docs/architecture/validation-and-delivery.md)
own check semantics. [Batch delivery](docs/workflows/agent-team-delivery.md) owns
parallel integration. Final review, delivery and release remain explicit;
a diagnostic or ready result grants none of them.

The repository's complete toolchain is in `mise.toml`; Node and Rust support
native acceptance tests, not Skill consumers. Run `mise trust mise.toml` after
reviewing it, then `mise install` and `uv sync --locked --all-extras --dev`.
Hosted CI uses the same declared final gate through `protocol test --gate final`,
without requiring private workspace records or issuing a lifecycle receipt.

Never commit credentials, caches, validation receipts or editor state.
