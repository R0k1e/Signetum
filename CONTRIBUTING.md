# Contributing

Use the [Signetum Skill](skills/signetum/SKILL.md) and the repository's `AGENTS.md`,
architecture entry and selected policies. Search existing production and test
owners before proposing a change. New work uses one `changes/<id>/change.toml`
and significant append history; generate its approval view and record actual
confirmation before implementation. Routine work creates no extra report or ADR.

Use an isolated member workspace and the declared uv environment. For focused
feedback, run `just test <affected-paths-or-pytest-options>`. Build with `uv build --clear`
before installed-artifact tests. `changed` explains selection without checks;
`ready` validates a committed member. Extend or consolidate existing tests at the
cheapest boundary that exposes the risk. Tell the user which tests change, why
and what evidence remains or replaces them; disclose relaxed assertions, skipped
coverage and threshold reductions separately in the existing review.

The [validation responsibilities](docs/architecture/validation-and-delivery.md)
own check semantics. [Batch delivery](docs/guide.md) owns
parallel integration. Final review, delivery and release remain explicit;
a diagnostic or ready result grants none of them.

The repository's complete toolchain is in `mise.toml`; Node and Rust support
native acceptance tests, not Skill consumers. Run `mise trust mise.toml` after
reviewing it, then `mise install` and `uv sync --locked --all-extras --dev`.
Portable runtime fixtures are derived from maintained source automatically before
pytest workers start; they are not committed code copies. Rendering also builds
them for a fresh scaffold. Hosted CI uses the declared final gate on Linux and macOS through one reusable
workflow, without private workspace records or lifecycle receipts. It enforces
90% project coverage after requiring every platform target. Local and selected
runs collect partial evidence rather than judging the whole project.

Never commit credentials, caches, validation receipts or editor state.

The repository enables the optional committed Python selector. `changed --explain`
shows the selected checks; unknown paths and dynamic reach conservatively retain
the full member suite. Documentation changes require traceability and relevant
static checks, rather than unconditional build and pytest. Final always executes
the full host suite. Require the complete hosted result for that exact candidate
before delivery.
